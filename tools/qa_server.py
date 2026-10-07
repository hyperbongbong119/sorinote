"""Isolated UI fixture server. No audio recording, no external API, no user library writes."""
import json
import os
import sys
import tempfile
import time
import io
import wave
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
qa=tempfile.TemporaryDirectory(prefix='sorinote-ui-')
os.environ['SORINOTE_DATA_DIR']=qa.name
os.environ['SORINOTE_HOME']=qa.name
os.environ['SORINOTE_ENV_FILE']=str(Path(qa.name)/'.env.local')
from backend.app import app,store,engine
from backend.capture import Capture
import backend.app as module
import uvicorn

class FixtureAI:
    def transcribe(self,*args):
        return '다음 주 월요일 웹사이트를 출시합니다. Alex가 체크리스트를 준비하고 예산은 추후 결정합니다.'
    def state(self,*args):
        return {'key_points':['월요일 웹사이트 출시','체크리스트 준비'], 'chapters':['[00:00:00] 출시 일정 논의']},None
    def summarize(self,*args):
        return '# QA 테스트 회의\n\n## 결정 사항\n- 다음 주 월요일 웹사이트 출시\n\n## 실행 항목\n- Alex: 체크리스트 준비\n\n## 질문\n- 예산 미정',None

class FixtureCapture(Capture):
    def start(self,mid):
        self.mid=mid
        p=store.folder(mid)/'audio'/'000001.wav'
        p.write_bytes(b'fixture-only-not-real-audio')
        store.execute("INSERT INTO chunks(meeting_id,seq,start,duration,rate,channels,path,status) VALUES(?,?,?,?,?,?,?,?)",(mid,1,0,30,16000,1,str(p),'pending'))
    def stop(self):
        if self.mid:
            store.update(self.mid,status='processing',ended=time.time())

engine.ai=FixtureAI()
engine.capture=FixtureCapture(store)
module.device_info=lambda *args:{'name':'QA fixture (no recording)','rate':16000,'channels':1}
module.list_sources=lambda:[{'id':'default','name':'기본 출력 (QA)','kind':'loopback'},{'id':'1'*24,'name':'테스트 마이크 (QA)','kind':'microphone'}]
buffer=io.BytesIO()
with wave.open(buffer,'wb') as wav:
    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\x00\x10'*80000)
module.sample_source=lambda source:(buffer.getvalue(),{'device':'테스트 입력 (QA)','duration':5,'peak':.125,'rms':.125,'has_signal':True,'seconds':5})
module.secrets=lambda:{**{v['env']:'fixture-only' for v in module.PROVIDERS.values()},'NOTION_TOKEN':''}
m=store.create('QA · 웹사이트 출시 회의','meeting')
store.update(m['id'],status='complete',ended=m['created']+1800,summary='### 강의 개요\n- **주제**: 웹사이트 출시 계획 [원문](#chunk-1)\n\n### 실행 계획\n- **출시 일정**: 다음 주 월요일 [원문](#chunk-1)\n  - Alex가 체크리스트 준비 [원문](#chunk-1)',state=json.dumps({'chapters':['[00:00:00] 출시 일정','[00:12:00] 업무 분담']}),cleaned=1)
store.execute("INSERT INTO chunks(meeting_id,seq,start,duration,rate,channels,path,status,text) VALUES(?,?,?,?,?,?,?,?,?)",(m['id'],1,0,1800,16000,1,'unused','done','다음 주 월요일에 출시하고 Alex가 체크리스트를 준비합니다.'))
store.export(m['id'])
try:
    uvicorn.run(app,host='127.0.0.1',port=18766,access_log=False)
finally:
    qa.cleanup()
