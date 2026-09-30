"""45-second local-only loopback check. Plays a synthetic fixture; never calls an API."""
import json
import sys
import tempfile
import time
import wave
import winsound
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.capture import Capture
from backend.store import Store

with tempfile.TemporaryDirectory(prefix='sorinote-capture-') as folder:
    store=Store(Path(folder))
    meeting=store.create('Local capture verification','general')
    capture=Capture(store)
    try:
        capture.start(meeting['id'])
        winsound.PlaySound(str(Path(sys.argv[1]).resolve()), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        time.sleep(45)
    finally:
        winsound.PlaySound(None,0)
        capture.stop()
    chunks=store.chunks(meeting['id'])
    peaks=[]
    for c in chunks:
        with wave.open(c['path'],'rb') as w:
            samples=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
        peaks.append(int(np.max(np.abs(samples.astype(float)))) if len(samples) else 0)
    assert len(chunks)>=2, 'Chunk boundary not crossed'
    assert all(c['status'] in ('pending','done') for c in chunks), 'Unsealed audio'
    assert not capture.error, capture.error
    assert any(p>100 for p in peaks), 'No system audio detected'
    assert sum(c['duration'] for c in chunks)>=40, 'Unexpected capture gap'
    print(json.dumps({'capture':'passed','chunks':len(chunks),'seconds':round(sum(c['duration'] for c in chunks),2),'peaks':peaks,'cloud_upload':False}))
