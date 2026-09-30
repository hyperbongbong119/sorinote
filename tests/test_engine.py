import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np

from backend.capture import Capture
from backend.engine import Engine
from backend.services import NotionService
from backend.store import Store


class FakeAI:
    fail = False
    def transcribe(self, path, context, settings):
        if self.fail:
            raise ConnectionError('offline')
        return '테스트 회의. 다음 주 출시하기로 결정했습니다.'
    def state(self, previous, chunks, settings):
        return {'key_points':['다음 주 출시'], 'chapters':['[00:00:00] 출시 논의']}, None
    def summarize(self, meeting, settings):
        return '# 테스트 회의\n\n## 결정 사항\n- 다음 주 출시', None


class DurabilityTests(unittest.TestCase):
    def test_provider_selection_is_frozen_for_existing_meeting(self):
        original=self.store.ai_settings(self.mid)
        self.store.set_settings({'stt_provider':'groq','stt_model':'whisper-large-v3-turbo','summary_provider':'anthropic','summary_model':'claude-haiku-4-5'})
        self.assertEqual(self.store.ai_settings(self.mid)['stt_provider'],original['stt_provider'])
        new=self.store.create('새 녹음','lecture')
        self.assertEqual(self.store.ai_settings(new['id'])['summary_provider'],'anthropic')

    def test_old_database_migrates_without_changing_meeting_content(self):
        self.store.update(self.mid,summary='기존 요약',notes='내 메모')
        self.store.execute('ALTER TABLE meetings DROP COLUMN ai_settings')
        reopened=Store(self.store.root)
        self.assertEqual(reopened.meeting(self.mid)['summary'],'기존 요약')
        self.assertEqual(reopened.meeting(self.mid)['notes'],'내 메모')
        self.assertEqual(reopened.ai_settings(self.mid)['summary_provider'],'openai')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))
        self.ai = FakeAI()
        self.engine = Engine(self.store,self.ai)
        self.mid = self.store.create('복구 테스트','meeting')['id']

    def chunk(self, seq=1, silent=False):
        p=self.store.folder(self.mid)/'audio'/f'{seq:06}.pcm'
        a=np.zeros(1600,dtype='<i2') if silent else np.full(1600,100,dtype='<i2')
        p.write_bytes(a.tobytes())
        cid=self.store.execute('INSERT INTO chunks(meeting_id,seq,start,rate,channels,path) VALUES(?,?,?,?,?,?)',
                             (self.mid,seq,(seq-1)*30,16000,1,str(p)))
        return self.store.query('SELECT * FROM chunks WHERE id=?',(cid,))[0]

    def finish(self):
        self.store.update(self.mid,status='processing',ended=time.time())
        self.engine.transcription_tick()
        self.engine.notes_tick()
        self.engine.notes_tick()

    def test_crash_recovers_raw_and_preserves_transcript_after_cleanup(self):
        self.chunk()
        self.store.recover()
        self.engine.capture.recover()
        self.assertEqual(self.store.meeting(self.mid)['status'],'interrupted')
        self.finish()
        m=self.store.meeting(self.mid)
        self.assertEqual(m['status'],'complete')
        self.assertTrue(m['cleaned'])
        self.assertFalse(Path(self.store.chunks(self.mid)[0]['path']).exists())
        for name in ('summary.md','transcript.md','meeting.json','metadata.json'):
            self.assertTrue((self.store.folder(self.mid)/name).is_file())
        self.assertIn('다음 주 출시',self.store.transcript(self.mid))

    def test_failure_retains_audio_and_prevents_later_context(self):
        for seq in (1,2):
            self.engine.capture.seal(self.chunk(seq))
        self.ai.fail=True
        self.engine.transcription_tick()
        self.engine.transcription_tick()
        chunks=self.store.chunks(self.mid)
        self.assertEqual(chunks[0]['attempts'],1)
        self.assertEqual(chunks[1]['attempts'],0)
        self.assertTrue(all(Path(c['path']).exists() for c in chunks))
        self.assertFalse(self.engine.cleanup(self.mid,manual=True))

    def test_upload_restart_does_not_duplicate_rows(self):
        self.engine.capture.seal(self.chunk())
        self.store.execute("UPDATE chunks SET status='uploading'")
        self.store.recover()
        self.finish()
        self.assertEqual(len(self.store.chunks(self.mid)),1)
        self.assertEqual(self.store.transcript(self.mid).count('테스트 회의'),1)

    def test_notion_failure_blocks_cleanup(self):
        self.engine.capture.seal(self.chunk())
        self.store.update(self.mid,notion_requested=1,notion_status='pending')
        with patch('backend.services.secrets',return_value={'NOTION_TOKEN':''}):
            self.finish()
        self.assertEqual(self.store.meeting(self.mid)['notion_status'],'failed')
        self.assertTrue(Path(self.store.chunks(self.mid)[0]['path']).exists())
        self.assertFalse(self.engine.cleanup(self.mid,manual=True))

    def test_notion_unknown_result_not_retried(self):
        self.store.update(self.mid,summary='테스트',notion_requested=1)
        self.store.set_settings({'notion_parent':'a'*32})
        with patch('backend.services.secrets',return_value={'NOTION_TOKEN':'fixture'}), patch('backend.services.httpx.Client') as client:
            post=client.return_value.__enter__.return_value.post
            post.side_effect=httpx.ReadTimeout('unknown remote result')
            self.engine.notion.send(self.mid)
            self.engine.notion.send(self.mid)
            self.assertEqual(post.call_count,1)
        self.assertEqual(self.store.meeting(self.mid)['notion_status'],'uncertain')

    def test_digital_silence_skipped_quiet_speech_kept(self):
        self.engine.capture.seal(self.chunk(1,silent=True))
        self.engine.capture.seal(self.chunk(2,silent=False))
        self.assertEqual([c['status'] for c in self.store.chunks(self.mid)],['done','pending'])

    def test_manual_retention_preserves_audio(self):
        self.store.set_settings({'retention':'manual'})
        self.engine.capture.seal(self.chunk())
        self.finish()
        self.assertEqual(self.store.meeting(self.mid)['status'],'complete')
        self.assertFalse(self.store.meeting(self.mid)['cleaned'])
        self.assertTrue(self.engine.cleanup(self.mid,manual=True))

    def test_export_contains_edit_and_valid_json(self):
        self.store.update(self.mid,title='편집한 제목',notes='내 메모',summary='수정된 요약')
        folder=self.store.export(self.mid)
        doc=json.loads((folder/'meeting.json').read_text(encoding='utf-8'))
        self.assertEqual(doc['notes'],'내 메모')
        self.assertEqual(doc['summary'],'수정된 요약')

    def test_missing_audio_never_marked_complete(self):
        row=self.chunk()
        Path(row['path']).unlink()
        self.engine.capture.seal(row)
        self.finish()
        self.assertEqual(self.store.chunks(self.mid)[0]['status'],'failed')
        self.assertNotEqual(self.store.meeting(self.mid)['status'],'complete')

    def test_four_hour_transcript_queue_keeps_all_480_chunks(self):
        # Time-compressed durability check, NOT a four-hour hardware soak test.
        with self.store.connect() as c:
            c.executemany("INSERT INTO chunks(meeting_id,seq,start,duration,rate,channels,path,status,text) VALUES(?,?,?,?,?,?,?,?,?)",
                [(self.mid,i,i*30,30,16000,1,'unused','done',f'발언 {i}: 중요한 기록입니다.') for i in range(1,481)])
        self.store.set_settings({'retention':'manual'})
        self.store.update(self.mid,status='processing',ended=time.time())
        for _ in range(5):
            self.engine.notes_tick()
        self.assertEqual(self.store.meeting(self.mid)['status'],'complete')
        transcript=self.store.transcript(self.mid)
        self.assertIn('발언 1:',transcript)
        self.assertIn('발언 480:',transcript)
        doc=json.loads((self.store.folder(self.mid)/'meeting.json').read_text(encoding='utf-8'))
        self.assertEqual(len(doc['transcript']),480)


if __name__=='__main__':
    unittest.main()
