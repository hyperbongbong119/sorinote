"""Deterministic failure injection: no network, hardware changes or user data."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from backend.capture import Capture, select_device, source_id, sample_source
from backend.engine import Engine
from backend.store import Store
from tests.test_engine import FakeAI


class ResilienceTests(unittest.TestCase):
    def test_selected_source_survives_device_index_changes_and_never_falls_back(self):
        d={'name':'My microphone','isLoopbackDevice':False,'maxInputChannels':1,'index':8}
        audio=MagicMock()
        audio.get_device_info_generator_by_host_api.return_value=[{**d,'index':15}]
        self.assertEqual(select_device(audio,source_id(d))['index'],15)
        audio.get_device_info_generator_by_host_api.return_value=[]
        with self.assertRaisesRegex(ValueError,'연결되어 있지'):
            select_device(audio,source_id(d))
        audio.get_default_wasapi_loopback.assert_not_called()

    def test_explicit_microphone_does_not_follow_default_output(self):
        d={'name':'My microphone','isLoopbackDevice':False,'maxInputChannels':1,'defaultSampleRate':16000,'index':8}
        self.engine.capture.source=source_id(d)
        audio=MagicMock();audio.get_device_info_generator_by_host_api.return_value=[d]
        fake_pa=SimpleNamespace(paInt16=8,paWASAPI=13,PyAudio=MagicMock())
        fake_pa.PyAudio.return_value.__enter__.return_value=audio
        with patch.dict(sys.modules,{'pyaudiowpatch':fake_pa}),patch.object(self.engine.capture,'_write_chunk',side_effect=lambda *args:self.engine.capture.stop_event.set()),patch('backend.capture.device_info') as default:
            self.engine.capture._record_device(self.mid)
        self.assertEqual(audio.open.call_args.kwargs['input_device_index'],8)
        default.assert_not_called()
        audio.open.return_value.close.assert_called_once()

    def test_preview_silence_is_bounded_and_closes_stream(self):
        audio=MagicMock()
        audio.get_default_wasapi_loopback.return_value={'name':'Silent speaker','maxInputChannels':2,'defaultSampleRate':48000,'index':4}
        audio.open.return_value.get_read_available.return_value=0
        fake_pa=SimpleNamespace(paInt16=8,PyAudio=MagicMock())
        fake_pa.PyAudio.return_value.__enter__.return_value=audio
        with patch.dict(sys.modules,{'pyaudiowpatch':fake_pa}),patch('backend.capture.time.monotonic',side_effect=[0,0,6]),patch('backend.capture.time.sleep'):
            wav,result=sample_source()
        self.assertTrue(wav.startswith(b'RIFF'))
        self.assertFalse(result['has_signal'])
        audio.open.return_value.read.assert_not_called()
        audio.open.return_value.close.assert_called_once()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.ai = FakeAI()
        self.engine = Engine(self.store, self.ai)
        self.mid = self.store.create('failure injection', 'meeting')['id']
        self.store.set_settings({'retention':'manual'})

    def enqueue(self, seq):
        path = self.store.folder(self.mid) / 'audio' / f'{seq:06}.wav'
        path.write_bytes(b'synthetic-test-fixture')
        self.store.execute("INSERT INTO chunks(meeting_id,seq,start,duration,rate,channels,path,status) VALUES(?,?,?,?,?,?,?,?)",
            (self.mid, seq, (seq-1)*30, 30, 16000, 1, str(path), 'pending'))

    def test_ten_minute_outage_keeps_recording_queue_then_recovers_in_order(self):
        self.ai.fail = True
        base = time.time()
        # Advance only worker clocks, never alter the Windows clock or adapter.
        for seq in range(1, 21):
            self.enqueue(seq)
            with patch('backend.engine.time.time', return_value=base+seq*30):
                self.engine.transcription_tick()
        rows = self.store.chunks(self.mid)
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(Path(c['path']).exists() for c in rows))
        self.assertTrue(all(c['attempts']==0 for c in rows[1:]))
        self.ai.fail = False
        for _ in range(20):
            with patch('backend.engine.time.time', return_value=base+1200):
                self.engine.transcription_tick()
        self.assertTrue(all(c['status']=='done' for c in self.store.chunks(self.mid)))
        self.store.update(self.mid, status='processing', ended=base+1200)
        for _ in range(3):
            self.engine.notes_tick()
        self.assertEqual(self.store.meeting(self.mid)['status'], 'complete')
        self.assertEqual(len(json.loads((self.store.folder(self.mid)/'meeting.json').read_text('utf-8'))['transcript']),20)

    def test_device_switch_closes_old_stream_and_records_warning(self):
        capture = self.engine.capture
        audio = MagicMock()
        audio.get_default_wasapi_loopback.return_value = {'name':'Speaker A','defaultSampleRate':48000,'maxInputChannels':2,'index':1}
        fake_pa = SimpleNamespace(paInt16=8, PyAudio=MagicMock())
        fake_pa.PyAudio.return_value.__enter__.return_value = audio
        with patch.dict(sys.modules, {'pyaudiowpatch':fake_pa}), patch.object(capture,'_write_chunk') as chunk, patch('backend.capture.device_info',return_value={'name':'Bluetooth B'}):
            capture._record_device(self.mid)
        chunk.assert_called_once()
        audio.open.return_value.close.assert_called_once()
        self.assertIn('변경', self.store.meeting(self.mid)['capture_warning'])

    def test_device_disconnect_retries_and_stops_cleanly(self):
        capture = self.engine.capture
        with patch.object(capture,'_record_device',side_effect=OSError('test unplug')), patch.object(capture.stop_event,'wait',side_effect=lambda _:capture.stop_event.set()):
            capture._run(self.mid)
        self.assertEqual(self.store.meeting(self.mid)['status'],'processing')
        self.assertIn('끊겨', self.store.meeting(self.mid)['capture_warning'])

    def test_silent_device_never_blocks_read_and_can_stop(self):
        capture = self.engine.capture
        stream = MagicMock()
        stream.get_read_available.return_value = 0
        with patch.object(capture.stop_event,'wait',return_value=True):
            capture._write_chunk(self.mid,stream,16000,1,1024)
        stream.read.assert_not_called()
        self.assertEqual(self.store.chunks(self.mid)[0]['status'],'done')

    def test_notion_success_allows_audio_cleanup(self):
        self.enqueue(1)
        self.store.set_settings({'notion_parent':'a'*32})
        self.store.update(self.mid,status='processing',ended=time.time(),notion_requested=1,notion_status='pending')
        self.engine.transcription_tick()
        response = httpx.Response(200,json={'id':'b'*32,'url':'https://notion.so/test'},request=httpx.Request('POST','https://api.notion.com/v1/pages'))
        with patch('backend.services.secrets',return_value={'NOTION_TOKEN':'fixture'}), patch('backend.services.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value=response
            client.return_value.__enter__.return_value.patch.return_value=response
            for _ in range(3):
                self.engine.notes_tick()
        self.assertEqual(self.store.meeting(self.mid)['notion_status'],'done')
        self.assertTrue(self.engine.cleanup(self.mid,manual=True))
