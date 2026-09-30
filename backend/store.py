"""Local source of truth. Each transaction has its own connection; no shared cursors."""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .providers import AI_FIELDS


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def stamp(seconds):
    value = max(0, int(seconds))
    return f'{value // 3600:02}:{value // 60 % 60:02}:{value % 60:02}'


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'library.sqlite3'
        self.export_lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meetings(
              id TEXT PRIMARY KEY, title TEXT NOT NULL, template TEXT NOT NULL,
              created REAL NOT NULL, ended REAL, status TEXT NOT NULL DEFAULT 'recording',
              summary TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
              tags TEXT NOT NULL DEFAULT '', favorite INTEGER NOT NULL DEFAULT 0,
              video_path TEXT NOT NULL DEFAULT '', notion_requested INTEGER NOT NULL DEFAULT 0,
              notion_id TEXT NOT NULL DEFAULT '', notion_url TEXT NOT NULL DEFAULT '',
              notion_status TEXT NOT NULL DEFAULT 'off', notion_cursor INTEGER NOT NULL DEFAULT 0,
              state TEXT NOT NULL DEFAULT '{}', state_until INTEGER NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '', retry_at REAL NOT NULL DEFAULT 0,
              cleaned INTEGER NOT NULL DEFAULT 0, folder TEXT NOT NULL,
              capture_warning TEXT NOT NULL DEFAULT '', input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS chunks(
              id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT NOT NULL REFERENCES meetings(id),
              seq INTEGER NOT NULL, start REAL NOT NULL, duration REAL NOT NULL DEFAULT 0,
              rate INTEGER NOT NULL, channels INTEGER NOT NULL, path TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'capturing', text TEXT NOT NULL DEFAULT '',
              attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '', UNIQUE(meeting_id,seq));
            CREATE INDEX IF NOT EXISTS queue_idx ON chunks(status,retry_at);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')
            if 'ai_settings' not in {r[1] for r in c.execute('PRAGMA table_info(meetings)')}:
                c.execute("ALTER TABLE meetings ADD COLUMN ai_settings TEXT NOT NULL DEFAULT '{}'")
                existing=self.settings()
                snapshot=json.dumps({k:existing[k] for k in AI_FIELDS})
                c.execute('UPDATE meetings SET ai_settings=?',(snapshot,))

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA synchronous=FULL')
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def query(self, sql, params=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def execute(self, sql, params=()):
        with self.connect() as c:
            return c.execute(sql, params).lastrowid

    def meeting(self, mid):
        rows = self.query('SELECT * FROM meetings WHERE id=?', (mid,))
        if not rows:
            raise KeyError('회의록을 찾을 수 없습니다.')
        return rows[0]

    def update(self, mid, **fields):
        # Field names only come from application-owned constants, never request keys.
        allowed = {'title','notes','tags','favorite','summary','video_path','status','ended','error',
                   'state','state_until','retry_at','notion_requested','notion_id','notion_url',
                   'notion_status','notion_cursor','cleaned','capture_warning','ai_settings'}
        if not fields.keys() <= allowed:
            raise ValueError('Unsupported field')
        self.execute('UPDATE meetings SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?',
                     (*fields.values(), mid))

    def create(self, title, template, notion=False):
        mid = uuid.uuid4().hex
        now = time.time()
        folder = time.strftime('%Y/%m/%Y-%m-%d_') + mid[:10]
        (self.root / 'MeetingNotes' / folder / 'audio').mkdir(parents=True)
        self.execute('INSERT INTO meetings(id,title,template,created,folder,notion_requested,notion_status) VALUES(?,?,?,?,?,?,?)',
                     (mid, title, template, now, folder, int(notion), 'pending' if notion else 'off'))
        self.update(mid,ai_settings=json.dumps({k:self.settings()[k] for k in AI_FIELDS}))
        self.export(mid)
        return self.meeting(mid)

    def folder(self, mid):
        return self.root / 'MeetingNotes' / self.meeting(mid)['folder']

    def chunks(self, mid):
        return self.query('SELECT * FROM chunks WHERE meeting_id=? ORDER BY seq', (mid,))

    def transcript(self, mid, anchors=False):
        return '\n\n'.join((f'<a id="chunk-{c["seq"]}"></a>\n' if anchors else '') + f'[{stamp(c["start"])}] {c["text"]}' for c in self.chunks(mid) if c['text'])

    def export(self, mid):
        with self.export_lock:
            m = self.meeting(mid)
            chunks = self.chunks(mid)
            folder = self.folder(mid)
            transcript = self.transcript(mid)
            atomic_text(folder / 'transcript.md', f'# {m["title"]}\n\n{self.transcript(mid, anchors=True)}\n')
            atomic_text(folder / 'summary.md', re.sub(r'\]\(#chunk-(\d+)\)',r'](transcript.md#chunk-\1)',m['summary']))
            metadata = {k: v for k, v in m.items() if k not in ('summary','state')}
            atomic_text(folder / 'metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))
            atomic_text(folder / 'meeting.json', json.dumps({**m, 'state': json.loads(m['state']),
                        'transcript': [{k:c[k] for k in ('seq','start','duration','text','status')} for c in chunks]},
                        ensure_ascii=False, indent=2))
            return folder

    def settings(self):
        defaults = {'stt_provider':'openai','summary_provider':'openai','stt_model':'gpt-4o-transcribe', 'summary_model':'gpt-5.6-luna',
                    'language':'ko', 'glossary':'', 'retention':'immediate',
                    'notion_parent':'', 'monthly_budget':'10'}
        defaults.update({r['key']:r['value'] for r in self.query('SELECT * FROM settings')})
        return defaults

    def ai_settings(self, mid):
        return {**self.settings(), **json.loads(self.meeting(mid)['ai_settings'])}

    def set_settings(self, values):
        with self.connect() as c:
            c.executemany('INSERT OR REPLACE INTO settings VALUES(?,?)', values.items())

    def recover(self):
        # Captured PCM is sealed by Capture.recover before workers are allowed to run.
        self.execute("UPDATE chunks SET status='pending' WHERE status='uploading'")
        self.execute("UPDATE meetings SET status='interrupted', ended=?, capture_warning='앱 종료로 녹음이 중단되었습니다. 저장된 오디오는 복구되었습니다.' WHERE status='recording'", (time.time(),))
        self.execute("UPDATE meetings SET status='processing' WHERE status='summarizing'")
        # An uncertain create/append must never be blindly retried: it may already exist remotely.
        self.execute("UPDATE meetings SET notion_status='uncertain', error='Notion 요청 도중 종료되었습니다. 원격 저장 결과를 확인하세요.' WHERE notion_status='sending'")
