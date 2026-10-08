import json
import threading
import time
from pathlib import Path

from .capture import Capture
from .services import AIService, NotionService, safe_error


class Engine:
    def __init__(self, store, ai=None):
        self.store = store
        self.capture = Capture(store)
        self.ai = ai or AIService()
        self.notion = NotionService(store)
        self.stop_event = threading.Event()
        self.threads = []
        self.last_error = ''
        self.note_lock = threading.RLock()
        self.transcription_lock = threading.RLock()

    def start(self):
        self.store.recover()
        self.capture.recover()
        for name, task in [('transcription', self.transcription_tick), ('meeting-notes', self.notes_tick)]:
            t = threading.Thread(target=self._loop, args=(task,), name=name, daemon=True)
            t.start()
            self.threads.append(t)

    def close(self):
        self.stop_event.set()
        self.capture.stop()
        for t in self.threads:
            t.join(timeout=2)

    def _loop(self, fn):
        while not self.stop_event.is_set():
            try:
                fn()
                self.last_error = ''
            except Exception as exc:
                self.last_error = safe_error(exc)
            self.stop_event.wait(1)

    def transcription_tick(self):
        with self.transcription_lock:
            self._transcription_tick()

    def _transcription_tick(self):
        # Never skip an earlier failed chunk in the same meeting: context stays chronological.
        rows = self.store.query('''SELECT c.* FROM chunks c WHERE c.status='pending' AND c.retry_at<=?
            AND EXISTS(SELECT 1 FROM meetings m WHERE m.id=c.meeting_id AND m.deleted_at=0)
            AND NOT EXISTS(SELECT 1 FROM chunks earlier WHERE earlier.meeting_id=c.meeting_id
                AND earlier.seq<c.seq AND earlier.status NOT IN ('done')) ORDER BY c.id LIMIT 1''', (time.time(),))
        if not rows:
            return
        c = rows[0]
        self.store.execute("UPDATE chunks SET status='uploading',attempts=attempts+1 WHERE id=?", (c['id'],))
        try:
            context = ' '.join(x['text'] for x in self.store.chunks(c['meeting_id']) if x['seq'] < c['seq'])[-1600:]
            text = self.ai.transcribe(c['path'], context, self.store.ai_settings(c['meeting_id']))
            # Each immutable chunk is stored once. Do not remove repeated speech heuristically.
            self.store.execute("UPDATE chunks SET status='done',text=?,error='',retry_at=0 WHERE id=?", (text,c['id']))
            self.store.export(c['meeting_id'])
        except Exception as exc:
            delay = min(300, 5 * 2 ** min(c['attempts'],6))
            self.store.execute("UPDATE chunks SET status='pending',error=?,retry_at=? WHERE id=?",
                               (safe_error(exc), time.time()+delay, c['id']))

    def _usage(self, mid, usage):
        if usage:
            self.store.execute('UPDATE meetings SET input_tokens=input_tokens+?,output_tokens=output_tokens+? WHERE id=?',
                               (usage.input_tokens, usage.output_tokens, mid))

    def notes_tick(self):
        with self.note_lock:
            self._notes_tick()

    def _notes_tick(self):
        meetings = self.store.query("SELECT * FROM meetings WHERE deleted_at=0 AND status IN ('recording','processing','interrupted','summarizing','complete') AND retry_at<=? ORDER BY created", (time.time(),))
        for m in meetings:
            mid = m['id']
            try:
                if m['status'] == 'complete':
                    if not m['cleaned']:
                        self.cleanup(mid)
                    continue
                chunks = self.store.chunks(mid)
                ready = []
                for c in chunks:
                    if c['status'] != 'done':
                        break
                    if c['seq'] > m['state_until']:
                        ready.append(c)
                final = m['status'] != 'recording' and all(c['status']=='done' for c in chunks)
                if ready and (final or sum(c['duration'] for c in ready)>=600):
                    batch, count = [], 0
                    for c in ready:
                        if batch and count + len(c['text']) > 30000:
                            break
                        batch.append(c)
                        count += len(c['text'])
                    if any(c['text'] for c in batch):
                        state, usage = self.ai.state(json.loads(m['state']), batch, self.store.ai_settings(mid))
                        self._usage(mid, usage)
                    else:
                        state = json.loads(m['state'])
                    self.store.update(mid, state=json.dumps(state,ensure_ascii=False), state_until=batch[-1]['seq'], error='')
                    self.store.export(mid)
                    continue
                if final and not m['summary'] and m['status'] != 'complete':
                    if not any(c['text'] for c in chunks):
                        summary, usage = '# 전사된 음성이 없습니다.\n\n시스템 출력 장치와 재생 중인 오디오를 확인하세요.', None
                    else:
                        self.store.update(mid, status='summarizing')
                        summary, usage = self.ai.summarize(self.store.meeting(mid), self.store.ai_settings(mid))
                    self._usage(mid, usage)
                    self.store.update(mid, summary=summary, status='processing', error='')
                    self.store.export(mid)
                    m = self.store.meeting(mid)
                if final and m['summary']:
                    if m['notion_requested'] and m['notion_status'] not in ('done','uncertain'):
                        self.notion.send(mid)
                        m = self.store.meeting(mid)
                    if not m['notion_requested'] or m['notion_status']=='done':
                        self.store.update(mid, status='complete', error='')
                        self.store.export(mid)
                        self.cleanup(mid)
            except Exception as exc:
                self.store.update(mid, error=safe_error(exc), retry_at=time.time()+60)

    def cleanup(self, mid, manual=False):
        m = self.store.meeting(mid)
        if m['cleaned'] or m['status'] != 'complete' or (m['notion_requested'] and m['notion_status']!='done'):
            return False
        if any(c['status'] != 'done' for c in self.store.chunks(mid)):
            return False
        policy = self.store.settings()['retention']
        hold = {'immediate':0, 'day':86400, 'week':604800}.get(policy)
        if not manual and (hold is None or time.time()-(m['ended'] or time.time()) < hold):
            return False
        # Ensure every permanent artifact is durable before deleting only this meeting's audio.
        folder = self.store.export(mid)
        audio_dir = (folder / 'audio').resolve()
        for c in self.store.chunks(mid):
            p = Path(c['path']).resolve()
            if p.parent != audio_dir or p.suffix not in ('.wav','.pcm'):
                raise ValueError('Unsafe audio path')
            p.unlink(missing_ok=True)
            p.with_suffix('.pcm').unlink(missing_ok=True)
        self.store.update(mid, cleaned=1)
        self.store.export(mid)
        return True
