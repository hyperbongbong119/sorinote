"""WASAPI capture with explicit loopback or microphone selection."""
import hashlib
import io
import os
import threading
import time
import wave
from pathlib import Path

import numpy as np


def source_id(d):
    kind='loopback' if d.get('isLoopbackDevice') else 'microphone'
    return hashlib.sha256((kind+'\0'+d['name']).encode()).hexdigest()[:24]


def input_devices(audio):
    import pyaudiowpatch as pa
    return [d for d in audio.get_device_info_generator_by_host_api(host_api_type=pa.paWASAPI)
            if d['maxInputChannels']>0]


def select_device(audio, source='default'):
    if source=='default':
        return audio.get_default_wasapi_loopback()
    for d in input_devices(audio):
        if source_id(d)==source:
            return d
    raise ValueError('선택한 입력 장치가 연결되어 있지 않습니다. 입력 소스를 다시 선택하세요.')


def list_sources():
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        return [{'id':'default','name':'시스템 기본 출력 · 자동 전환','kind':'loopback'}]+[
            {'id':source_id(d),'name':d['name'],'kind':'loopback' if d.get('isLoopbackDevice') else 'microphone'}
            for d in input_devices(audio)]


def device_info(source='default'):
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        d = select_device(audio, source)
        return {'name': d['name'], 'rate': int(d['defaultSampleRate']), 'channels': d['maxInputChannels']}


def sample_source(source='default', seconds=5):
    """Bounded local preview; no library writes and no external API calls."""
    import pyaudiowpatch as pa
    packets=[]
    with pa.PyAudio() as audio:
        d=select_device(audio,source)
        rate,channels=int(d['defaultSampleRate']),int(d['maxInputChannels'])
        stream=audio.open(format=pa.paInt16,channels=channels,rate=rate,input=True,
                          input_device_index=d['index'],frames_per_buffer=1024)
        try:
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                available=stream.get_read_available()
                if available:
                    packets.append(stream.read(min(1024,available),exception_on_overflow=True))
                else:
                    time.sleep(.02)
        finally:
            stream.close()
    pcm=b''.join(packets)
    samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)
    peak=float(np.max(np.abs(samples))/32768) if len(samples) else 0.
    rms=float(np.sqrt(np.mean(samples**2))/32768) if len(samples) else 0.
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setnchannels(channels);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
    return buffer.getvalue(),{'device':d['name'],'duration':len(pcm)/2/channels/rate,
                             'peak':peak,'rms':rms,'has_signal':rms>=.001,'seconds':seconds}


class Capture:
    def __init__(self, store):
        self.store = store
        self.thread = None
        self.stop_event = threading.Event()
        self.mid = None
        self.level = 0.0
        self.device = ''
        self.error = ''
        self.lock = threading.Lock()
        self.source = 'default'

    def start(self, mid):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('이미 녹음 중입니다.')
            self.mid, self.error = mid, ''
            self.source = self.store.settings().get('audio_source','default')
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, args=(mid,), daemon=True, name='wasapi-capture')
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise ValueError('오디오 장치 종료를 기다리는 중입니다. 잠시 후 다시 시도하세요.')

    def seal(self, row):
        raw = Path(row['path'])
        if not raw.exists():
            self.store.execute("UPDATE chunks SET status='failed',error='오디오 파일이 없습니다.' WHERE id=?", (row['id'],))
            return
        pcm = raw.read_bytes()
        frame_size = 2 * row['channels']
        pcm = pcm[:len(pcm) // frame_size * frame_size]
        wav = raw.with_suffix('.wav')
        tmp = raw.with_suffix('.wav.tmp')
        with wave.open(str(tmp), 'wb') as f:
            f.setnchannels(row['channels'])
            f.setsampwidth(2)
            f.setframerate(row['rate'])
            f.writeframes(pcm)
        with tmp.open('rb+') as f:
            os.fsync(f.fileno())
        os.replace(tmp, wav)
        duration = len(pcm) / frame_size / row['rate']
        # Only exact digital silence is skipped; quiet speech must still reach STT.
        silent = not pcm or not np.any(np.frombuffer(pcm, dtype='<i2'))
        self.store.execute('UPDATE chunks SET duration=?,path=?,status=? WHERE id=?',
                           (duration, str(wav), 'done' if silent else 'pending', row['id']))
        raw.unlink(missing_ok=True)

    def recover(self):
        for row in self.store.query("SELECT * FROM chunks WHERE status='capturing'"):
            self.seal(row)

    def _record_device(self, mid):
        import pyaudiowpatch as pa
        # Keep the stream open across chunks. Only reopen if Windows changes output.
        with pa.PyAudio() as audio:
            d = select_device(audio, self.source)
            self.device = d['name']
            rate, channels = int(d['defaultSampleRate']), int(d['maxInputChannels'])
            if not channels:
                raise RuntimeError('No loopback channels')
            block = 1024
            stream = audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                                input_device_index=d['index'], frames_per_buffer=block)
            try:
                while not self.stop_event.is_set():
                    self._write_chunk(mid, stream, rate, channels, block)
                    if self.stop_event.is_set():
                        break
                    if self.source=='default' and device_info()['name'] != d['name']:
                        self.store.update(mid, capture_warning=f'{time.strftime("%H:%M:%S")} 기본 출력 장치를 변경했습니다. 전환 구간에 짧은 공백이 있을 수 있습니다.')
                        break
            finally:
                stream.close()

    def _write_chunk(self, mid, stream, rate, channels, block):
        seq = self.store.query('SELECT COALESCE(MAX(seq),0)+1 AS n FROM chunks WHERE meeting_id=?', (mid,))[0]['n']
        raw = self.store.folder(mid) / 'audio' / f'{seq:06}.pcm'
        start = time.time() - self.store.meeting(mid)['created']
        cid = self.store.execute('INSERT INTO chunks(meeting_id,seq,start,rate,channels,path) VALUES(?,?,?,?,?,?)',
                                 (mid, seq, start, rate, channels, str(raw)))
        row = self.store.query('SELECT * FROM chunks WHERE id=?', (cid,))[0]
        elapsed, quiet, synced = 0., 0., 0.
        last_packet = time.monotonic()
        try:
            with raw.open('wb', buffering=0) as f:
                while not self.stop_event.is_set():
                    available = stream.get_read_available()
                    if available:
                        data = stream.read(min(block, available), exception_on_overflow=True)
                        last_packet = time.monotonic()
                    else:
                        # WASAPI may deliver no packets when all applications are silent.
                        # Never block Stream.read waiting for a packet: stop must still work.
                        if self.stop_event.wait(.02):
                            break
                        now = time.monotonic()
                        if now-last_packet < .2:
                            continue
                        data = bytes(int((now-last_packet)*rate) * channels * 2)
                        last_packet = now
                    f.write(data)
                    rms = float(np.sqrt(np.mean(np.frombuffer(data, dtype='<i2').astype(np.float32) ** 2))) / 32768
                    self.level = min(1., rms * 10)
                    dt = len(data) / 2 / channels / rate
                    elapsed += dt
                    quiet = quiet + dt if rms < 0.008 else 0
                    if elapsed - synced >= 1:
                        os.fsync(f.fileno())
                        synced = elapsed
                    # Energy-based end-of-utterance detection (not a speech classifier).
                    if elapsed >= 40 or (elapsed >= 20 and quiet >= .8):
                        break
                os.fsync(f.fileno())
        finally:
            self.seal(row)

    def _run(self, mid):
        try:
            while not self.stop_event.is_set():
                try:
                    self._record_device(mid)
                    self.error = ''
                except Exception as exc:
                    self.error = f'오디오 연결 재시도 중 ({type(exc).__name__})'
                    self.store.update(mid, capture_warning=f'{time.strftime("%H:%M:%S")} 오디오 연결이 끊겨 일부 구간이 누락될 수 있습니다.')
                    self.stop_event.wait(3)
        finally:
            self.level = 0
            self.store.update(mid, status='processing', ended=time.time())
            self.store.export(mid)
