"""Real-time WASAPI soak, local only; temporary captured audio is erased on exit."""
import json
import tempfile
import time
import wave
from pathlib import Path


def run(seconds, report):
    from backend.capture import Capture
    from backend.store import Store
    if not 10 <= seconds <= 86400:
        raise ValueError('Duration must be 10..86400 seconds')
    started = time.monotonic()
    samples = []
    interrupted = False
    with tempfile.TemporaryDirectory(prefix='sorinote-soak-') as folder:
        store = Store(Path(folder))
        capture = Capture(store)
        mid = store.create('Hardware soak (local only)', 'general')['id']
        capture.start(mid)
        try:
            while time.monotonic()-started < seconds:
                samples.append({'seconds':round(time.monotonic()-started,2),'device':capture.device,'error':capture.error,'level':capture.level})
                time.sleep(min(1, max(0, seconds-(time.monotonic()-started))))
        except KeyboardInterrupt:
            interrupted = True
        finally:
            capture.stop()
        elapsed = time.monotonic()-started
        chunks = store.chunks(mid)
        durations = []
        for c in chunks:
            with wave.open(c['path'], 'rb') as wav:
                durations.append(wav.getnframes()/wav.getframerate())
        devices = list(dict.fromkeys(s['device'] for s in samples if s['device']))
        captured = sum(durations)
        result = {'passed':not interrupted and captured >= seconds*.97 and all(c['status'] in ('pending','done') for c in chunks),
                  'requested_seconds':seconds,'elapsed_seconds':round(elapsed,2),'captured_seconds':round(captured,2),
                  'chunks':len(chunks),'observed_devices':devices,'device_switch_observed':len(devices)>1,
                  'audio_signal_observed':any(s['level']>.001 for s in samples),
                  'interrupted':interrupted,'cloud_upload':False,'temporary_audio_deleted':True,
                  'warnings':list(dict.fromkeys(s['error'] for s in samples if s['error'])),
                  'note':'Continuity check only. Semantic accuracy, video-app performance and unobserved device switches are not verified.'}
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    import argparse
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=14400)
    parser.add_argument('--report',type=Path,default=Path('docs/verification-soak.json'))
    args=parser.parse_args()
    result=run(args.seconds,args.report)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
