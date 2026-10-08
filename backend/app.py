import json
import base64
import tempfile
import os
import re
import secrets as tokenlib
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import set_key
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .capture import device_info, list_sources, sample_source
from .engine import Engine
from .services import ROOT, safe_error, secrets
from .store import Store
from .paths import DATA_DIR, ENV_FILE, prepare
from .providers import PROVIDERS, STT_MODELS, AI_FIELDS, list_models

prepare()
store = Store(DATA_DIR)
engine = Engine(store)
token = tokenlib.token_urlsafe(32)
start_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    # One owner of the durable queue, even if a second launcher uses another port.
    lock = (store.root / 'engine.lock').open('a+b')
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    engine.start()
    yield
    engine.close()
    lock.close()


app = FastAPI(title='Sorinote', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','testserver'])


@app.middleware('http')
async def local_access(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin not in
                (str(request.base_url).rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173')):
            return JSONResponse({'detail':'외부 사이트에서 접근할 수 없습니다.'}, status_code=403)
        if request.method == 'OPTIONS':
            return Response(status_code=403)
        if request.url.path != '/api/bootstrap' and not tokenlib.compare_digest(request.headers.get('x-sorinote-token',''),token):
            return JSONResponse({'detail':'앱을 새로고침하세요.'}, status_code=403)
        if request.url.path.startswith('/api/meetings/') and not request.url.path.endswith('/restore'):
            mid=request.url.path.split('/')[3]
            if store.query('SELECT id FROM meetings WHERE id=? AND deleted_at>0',(mid,)):
                return JSONResponse({'detail':'삭제된 회의록입니다. 먼저 복원하세요.'},status_code=404)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(KeyError)
async def missing(request, exc):
    return JSONResponse({'detail':'회의록을 찾을 수 없습니다.'},status_code=404)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default errors echo input values, which may include a credential.
    return JSONResponse({'detail':'입력 형식이나 길이를 확인하세요.'},status_code=422)


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail':str(exc)},status_code=400)


class NewMeeting(BaseModel):
    title: str = Field(default='새로운 회의', min_length=1,max_length=200)
    template: Literal['meeting','lecture','interview','general'] = 'meeting'
    notion: bool = False


class EditMeeting(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None,min_length=1,max_length=200)
    summary: str | None = Field(default=None,max_length=200000)
    notes: str | None = Field(default=None,max_length=100000)
    tags: str | None = Field(default=None,max_length=1000)
    favorite: bool | None = None
    video_path: str | None = Field(default=None,max_length=2000)


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stt_provider: Literal['openai','groq','gemini'] = 'openai'
    summary_provider: Literal['openai','groq','gemini','anthropic','openrouter','deepseek','mistral','xai'] = 'openai'
    stt_model: str = Field(default='gpt-4o-transcribe',min_length=1,max_length=100)
    summary_model: str = Field(default='gpt-5.6-luna',min_length=1,max_length=160,pattern=r'^[a-zA-Z0-9._:/-]+$')
    language: str = Field(default='ko',max_length=5,pattern=r'^[a-z-]*$')
    audio_source: str = Field(default='default',pattern=r'^(default|[a-f0-9]{24})$')
    glossary: str = Field(default='',max_length=1500)
    retention: Literal['immediate','day','week','manual'] = 'immediate'
    notion_parent: str = Field(default='',max_length=2000)
    monthly_budget: str = Field(default='10',max_length=12,pattern=r'^\d+(\.\d+)?$')
    openai_key: str = Field(default='',max_length=1000)
    groq_key: str = Field(default='',max_length=1000)
    gemini_key: str = Field(default='',max_length=1000)
    anthropic_key: str = Field(default='',max_length=1000)
    openrouter_key: str = Field(default='',max_length=1000)
    deepseek_key: str = Field(default='',max_length=1000)
    mistral_key: str = Field(default='',max_length=1000)
    xai_key: str = Field(default='',max_length=1000)
    notion_token: str = Field(default='',max_length=1000)


def detail(mid):
    m = store.meeting(mid)
    if m['deleted_at']:
        raise KeyError(mid)
    chunks = store.chunks(mid)
    return {**m, 'state':json.loads(m['state']), 'transcript':store.transcript(mid),
            'chunks':[{k:c[k] for k in ('id','seq','start','duration','status','text','error','attempts')} for c in chunks],
            'local_path':str(store.folder(mid))}


@app.get('/api/bootstrap')
def bootstrap():
    return {'app':'sorinote', 'token':token}


@app.get('/api/status')
def status():
    current = store.query("SELECT id FROM meetings WHERE status='recording' ORDER BY created DESC LIMIT 1")
    counts = store.query("SELECT count(*) AS n FROM chunks c JOIN meetings m ON m.id=c.meeting_id WHERE c.status NOT IN ('done') AND m.deleted_at=0")[0]['n']
    keys = secrets()
    configured = {p:bool(keys.get(v['env'])) for p,v in PROVIDERS.items()}
    settings = store.settings()
    return {'recording': bool(current), 'current_id':current[0]['id'] if current else None,
            'level':engine.capture.level, 'device':engine.capture.device,
            'capture_error':engine.capture.error, 'worker_error':engine.last_error,
            'queued':counts, 'openai_configured':bool(keys['OPENAI_API_KEY']),
            'providers_configured':configured,
            'ai_configured':configured[settings['stt_provider']] and configured[settings['summary_provider']],
            'notion_configured':bool(keys['NOTION_TOKEN'] and store.settings()['notion_parent']),
            'data_dir':str(store.root), 'settings':store.settings()}


@app.get('/api/device')
def device():
    try:
        return device_info(store.settings()['audio_source'])
    except Exception as exc:
        raise HTTPException(503, f'시스템 오디오 장치를 확인할 수 없습니다 ({type(exc).__name__}).')


class SourceTest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source: str = Field(default='default',pattern=r'^(default|[a-f0-9]{24})$')
    transcribe: bool = False


@app.put('/api/audio/source')
def set_source(body: SourceTest):
    with start_lock:
        if store.query("SELECT id FROM meetings WHERE status='recording'"):
            raise HTTPException(409,'녹음을 종료한 뒤 입력 소스를 변경하세요.')
        try:
            device_info(body.source)
        except ValueError:
            raise
        except Exception:
            raise HTTPException(503,'입력 장치를 사용할 수 없습니다. 연결 상태를 확인하세요.')
        store.set_settings({'audio_source':body.source})
    return {'ok':True}


@app.get('/api/audio/sources')
def audio_sources():
    try:
        return {'sources':list_sources()}
    except Exception as exc:
        raise HTTPException(503,f'입력 장치 목록을 확인할 수 없습니다 ({type(exc).__name__}).')


@app.post('/api/audio/test')
def test_source(body: SourceTest):
    settings=store.settings()
    # The same lock prevents recording from starting while a preview owns the device.
    with start_lock:
        if store.query("SELECT id FROM meetings WHERE status='recording'"):
            raise HTTPException(409,'녹음을 종료한 뒤 입력 소스를 테스트하세요.')
        try:
            wav,result=sample_source(body.source)
        except ValueError:
            raise
        except Exception as exc:
            raise HTTPException(503,f'입력 장치를 열 수 없습니다 ({type(exc).__name__}). 장치 연결과 마이크 권한을 확인하세요.')
    result['audio']='data:audio/wav;base64,'+base64.b64encode(wav).decode('ascii')
    if body.transcribe and result['has_signal']:
        try:
            with tempfile.TemporaryDirectory(prefix='sorinote-source-test-') as folder:
                path=Path(folder)/'sample.wav';path.write_bytes(wav)
                result['transcript']=engine.ai.transcribe(path,'',settings)
        except Exception as exc:
            # Keep preview available even if the selected API fails.
            result['api_error']=safe_error(exc)
    return result


@app.get('/api/meetings')
def meetings(q: str = '', favorite: bool = False, deleted: bool = False):
    rows = store.query('''SELECT m.*, (SELECT count(*) FROM chunks c WHERE c.meeting_id=m.id AND c.status!='done') AS pending
        FROM meetings m WHERE (?='' OR instr(lower(m.title||m.summary||m.notes||m.tags),lower(?))>0
        OR EXISTS(SELECT 1 FROM chunks c WHERE c.meeting_id=m.id AND instr(lower(c.text),lower(?))>0))
        AND (?=0 OR favorite=1) AND ((?=0 AND deleted_at=0) OR (?=1 AND deleted_at>0)) ORDER BY created DESC''',(q,q,q,int(favorite),int(deleted),int(deleted)))
    return [{k:v for k,v in r.items() if k not in ('summary','state','notes')} for r in rows]


@app.get('/api/meetings/{mid}')
def get_meeting(mid: str):
    return detail(mid)


@app.post('/api/recording/start')
def start(body: NewMeeting):
    with start_lock:
        if (engine.capture.thread and engine.capture.thread.is_alive()) or store.query("SELECT id FROM meetings WHERE status='recording'"):
            raise HTTPException(409,'이미 녹음 중입니다.')
        device()  # Fail before creating a meeting if there is no loopback endpoint.
        if body.notion and not (secrets()['NOTION_TOKEN'] and store.settings()['notion_parent']):
            raise ValueError('설정에서 Notion을 먼저 연결하세요.')
        m = store.create(body.title.strip() or '새로운 회의', body.template, body.notion)
        engine.capture.start(m['id'])
        return detail(m['id'])


@app.post('/api/recording/stop')
def stop():
    with start_lock:
        engine.capture.stop()
    return {'ok':True, 'id':engine.capture.mid}


@app.patch('/api/meetings/{mid}')
def edit(mid: str, body: EditMeeting):
    with engine.note_lock:
        detail(mid)
        m = store.meeting(mid)
        values = body.model_dump(exclude_none=True)
        if 'title' in values:
            values['title'] = values['title'].strip()
            if not values['title']:
                raise ValueError('제목을 입력하세요.')
        if 'summary' in values and m['status'] != 'complete':
            raise ValueError('자동 처리가 완료된 후 요약을 편집하세요.')
        if values:
            store.update(mid, **values)
            store.export(mid)
        return detail(mid)


@app.delete('/api/meetings/{mid}')
def delete_meeting(mid: str):
    with start_lock, engine.transcription_lock, engine.note_lock:
        m=store.meeting(mid)
        if m['status']=='recording':
            raise HTTPException(409,'녹음을 종료한 뒤 삭제하세요.')
        store.update(mid,deleted_at=time.time())
        store.export(mid)
    return {'ok':True}


@app.post('/api/meetings/{mid}/restore')
def restore_meeting(mid: str):
    with engine.transcription_lock, engine.note_lock:
        store.meeting(mid)
        store.update(mid,deleted_at=0)
        store.export(mid)
    return detail(mid)


@app.post('/api/meetings/{mid}/retry')
def retry(mid: str):
    store.meeting(mid)
    store.execute("UPDATE chunks SET retry_at=0 WHERE meeting_id=? AND status='pending'", (mid,))
    store.update(mid, retry_at=0, error='')
    return {'ok':True}


@app.post('/api/meetings/{mid}/regenerate')
def regenerate(mid: str):
    with engine.note_lock:
        m = store.meeting(mid)
        if m['status'] != 'complete' or any(c['status'] != 'done' for c in store.chunks(mid)):
            raise ValueError('전사와 기존 처리가 완료된 기록만 다시 요약할 수 있습니다.')
        from .store import atomic_text
        backup = store.folder(mid) / ('summary-backup-' + tokenlib.token_hex(6) + '.json')
        atomic_text(backup, json.dumps({'summary':m['summary'],'state':m['state']},ensure_ascii=False))
        selected = json.loads(m['ai_settings'])
        settings = store.settings()
        selected.update({k:settings[k] for k in ('summary_provider','summary_model')})
        store.update(mid,summary='',state='{}',state_until=0,status='processing',retry_at=0,error='',notion_requested=0,ai_settings=json.dumps(selected))
        store.export(mid)
        return detail(mid)


@app.post('/api/meetings/{mid}/notion')
def sync_notion(mid: str):
    with engine.note_lock:
        m = store.meeting(mid)
        if not m['summary']:
            raise ValueError('요약 생성 후 Notion에 보낼 수 있습니다.')
        if m['notion_status']=='uncertain':
            raise ValueError('이전 Notion 요청 결과가 불확실합니다. 원격 페이지를 확인하세요. 로컬 원본은 보존됩니다.')
        # A resend appends a clearly dated snapshot without deleting user edits on Notion.
        if m['notion_status']=='done':
            from .store import atomic_text
            text = f'\n업데이트 · {time.strftime("%Y-%m-%d %H:%M")}\n\n' + m['summary']+'\n\n'+store.transcript(mid)
            blocks = [{'object':'block','type':'paragraph','paragraph':{'rich_text':[{'type':'text','text':{'content':text[i:i+1500]}}]}} for i in range(0,len(text),1500)]
            atomic_text(store.folder(mid)/'notion-payload.json', json.dumps(blocks,ensure_ascii=False))
            store.update(mid, notion_cursor=0)
        store.update(mid, notion_requested=1, notion_status='pending', status='processing', retry_at=0, error='')
        return {'ok':True}


@app.post('/api/meetings/{mid}/cleanup')
def cleanup(mid: str):
    with engine.note_lock:
        if not engine.cleanup(mid, manual=True):
            raise ValueError('모든 전사·요약·선택한 Notion 저장이 완료되어야 오디오를 정리할 수 있습니다.')
    return {'ok':True}


@app.get('/api/meetings/{mid}/export/{kind}')
def export(mid: str, kind: Literal['md','txt','json']):
    m = store.meeting(mid)
    folder = store.export(mid)
    if kind=='json':
        return FileResponse(folder / 'meeting.json', filename=f'sorinote-{mid[:8]}.json')
    text = f'# {m["title"]}\n\n{m["summary"]}\n\n## 메모\n{m["notes"]}\n\n## 전사 원문\n{store.transcript(mid, anchors=kind=="md")}'
    return Response(text,media_type='text/plain; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="sorinote-{mid[:8]}.{kind}"'})


@app.post('/api/meetings/{mid}/open-folder')
def open_folder(mid: str):
    os.startfile(str(store.folder(mid)))
    return {'ok':True}


@app.post('/api/meetings/{mid}/open-video')
def open_video(mid: str):
    p = Path(store.meeting(mid)['video_path'])
    if not p.is_absolute() or str(p).startswith('\\\\') or p.suffix.lower() not in ('.mp4','.mkv','.mov','.webm','.avi','.wmv') or not p.is_file():
        raise ValueError('로컬 동영상 파일의 전체 경로를 입력하세요.')
    os.startfile(str(p))
    return {'ok':True}


@app.put('/api/settings')
def save_settings(body: Settings):
    values = body.model_dump()
    if values['stt_model'] not in STT_MODELS[values['stt_provider']]:
        raise ValueError('전사 서비스와 모델 조합을 확인하세요.')
    pending_keys = {}
    key_fields = [(p+'_key',v['env'],'sk-' if p=='openai' else None) for p,v in PROVIDERS.items()] + [('notion_token','NOTION_TOKEN',None)]
    for field, name, prefix in key_fields:
        value = values.pop(field).strip()
        if value:
            if '\n' in value or '\r' in value or (prefix and not value.startswith(prefix)):
                raise ValueError('키 형식을 확인하세요.')
            pending_keys[name] = value
    parent = values['notion_parent'].strip()
    if parent:
        match = re.search(r'([a-fA-F0-9]{32}|[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12})(?:[/?#]|$)',parent)
        if not match:
            raise ValueError('올바른 Notion 페이지 ID 또는 링크를 입력하세요.')
        values['notion_parent'] = match.group(1)
    for name, value in pending_keys.items():
        set_key(str(ENV_FILE), name, value)
    store.set_settings(values)
    return {'ok':True}


@app.post('/api/settings/models/{provider}')
def provider_models(provider: Literal['openai','groq','gemini','anthropic','openrouter','deepseek','mistral','xai']):
    try:
        return {'models':list_models(provider,secrets()),'provider':provider}
    except Exception as exc:
        raise HTTPException(400,safe_error(exc))


class SummaryTest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider: Literal['openai','groq','gemini','anthropic','openrouter','deepseek','mistral','xai']
    model: str = Field(min_length=1,max_length=160,pattern=r'^[a-zA-Z0-9._:/-]+$')


@app.post('/api/settings/test-summary')
def test_summary_model(body: SummaryTest | None = None):
    try:
        settings=store.settings()
        if body:
            settings={**settings,'summary_provider':body.provider,'summary_model':body.model}
        state, usage = engine.ai.state({},[{'seq':1,'start':0,'text':'연결 테스트입니다. 다음 주 월요일에 회의합니다.'}],settings)
        summary, final_usage=engine.ai.summarize({'title':'API 연결 테스트','template':'meeting','state':json.dumps(state,ensure_ascii=False)},settings)
        return {'ok':True,'summary':summary,'provider':settings['summary_provider'],'model':settings['summary_model'],
                'input_tokens':sum(u.input_tokens for u in (usage,final_usage) if u),
                'output_tokens':sum(u.output_tokens for u in (usage,final_usage) if u)}
    except Exception as exc:
        raise HTTPException(400,safe_error(exc))


@app.post('/api/shutdown')
def shutdown():
    if engine.capture.thread and engine.capture.thread.is_alive():
        raise ValueError('녹음을 먼저 종료하세요.')
    callback = getattr(app.state,'request_shutdown',None)
    if callback:
        callback()
        return {'ok':True}
    raise HTTPException(409,'현재 실행 방식에서는 터미널에서 종료하세요.')


@app.post('/api/settings/check-openai')
def check_openai():
    try:
        with engine.ai.client() as client:
            models = {m.id for m in client.models.list().data}
        settings = store.settings()
        return {'ok':True, 'stt_available':settings['stt_model'] in models,
                'summary_available':settings['summary_model'] in models}
    except Exception as exc:
        raise HTTPException(400,safe_error(exc))


if (ROOT / 'dist').exists():
    app.mount('/', StaticFiles(directory=ROOT / 'dist',html=True),name='ui')
