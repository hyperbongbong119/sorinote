import os
import tempfile
import unittest
from unittest.mock import patch
from dotenv import dotenv_values
from pathlib import Path

# Set before importing the app, so no test ever touches the user's library.
tmp = tempfile.TemporaryDirectory()
os.environ['SORINOTE_DATA_DIR']=tmp.name
from backend.app import app, store, token
from fastapi.testclient import TestClient


class LocalApiTests(unittest.TestCase):
    def test_gemini_stt_and_new_summary_keys_persist_without_leaking(self):
        with tempfile.TemporaryDirectory() as d:
            env=Path(d)/'.env.local'
            with patch('backend.app.ENV_FILE',env),patch('backend.services.ENV_FILE',env):
                for provider in ('deepseek','mistral','xai'):
                    response=self.client.put('/api/settings',headers=self.headers,json={'stt_provider':'gemini','stt_model':'gemini-2.5-flash-lite','gemini_key':'gemini-fixture-secret','summary_provider':provider,'summary_model':'test-model',provider+'_key':'provider-fixture-secret'})
                    self.assertEqual(response.status_code,200)
                    state=self.client.get('/api/status',headers=self.headers)
                    self.assertTrue(state.json()['ai_configured'])
                    self.assertEqual(state.json()['settings']['stt_provider'],'gemini')
                    self.assertNotIn('fixture-secret',state.text)
                    self.assertNotIn('fixture-secret',str(store.settings()))
                self.assertEqual(dotenv_values(env)['DEEPSEEK_API_KEY'],'provider-fixture-secret')
                self.client.put('/api/settings',headers=self.headers,json={})

    def test_blank_title_rejected_and_trimmed_title_saved(self):
        m=store.create('제목','meeting')
        self.assertEqual(self.client.patch('/api/meetings/'+m['id'],headers=self.headers,json={'title':'   '}).status_code,400)
        response=self.client.patch('/api/meetings/'+m['id'],headers=self.headers,json={'title':'  바꾼 제목  '})
        self.assertEqual(response.json()['title'],'바꾼 제목')

    def test_provider_keys_never_enter_settings_database_or_response(self):
        with tempfile.TemporaryDirectory() as d:
            env=Path(d)/'.env.local'
            with patch('backend.app.ENV_FILE',env),patch('backend.services.ENV_FILE',env):
                response=self.client.put('/api/settings',headers=self.headers,json={'groq_key':'fixture-secret-groq','anthropic_key':'fixture-secret-claude','stt_provider':'groq','stt_model':'whisper-large-v3-turbo','summary_provider':'anthropic','summary_model':'claude-haiku-4-5'})
                self.assertEqual(response.status_code,200)
                self.assertEqual(dotenv_values(env)['GROQ_API_KEY'],'fixture-secret-groq')
                state=self.client.get('/api/status',headers=self.headers)
                self.assertTrue(state.json()['ai_configured'])
                self.assertNotIn('fixture-secret',state.text)
                self.assertNotIn('fixture-secret',str(store.settings()))
                self.client.put('/api/settings',headers=self.headers,json={})
                self.assertEqual(dotenv_values(env)['GROQ_API_KEY'],'fixture-secret-groq')

    def test_invalid_stt_combination_does_not_write_key(self):
        with tempfile.TemporaryDirectory() as d,patch('backend.app.ENV_FILE',Path(d)/'.env.local'):
            response=self.client.put('/api/settings',headers=self.headers,json={'stt_provider':'groq','stt_model':'gpt-4o-transcribe','groq_key':'do-not-save'})
            self.assertEqual(response.status_code,400)
            self.assertFalse((Path(d)/'.env.local').exists())

    @classmethod
    def tearDownClass(cls):
        tmp.cleanup()

    def setUp(self):
        self.client=TestClient(app)
        self.headers={'X-Sorinote-Token':token}

    def test_external_origin_and_missing_token_blocked(self):
        self.assertEqual(self.client.get('/api/status').status_code,403)
        self.assertEqual(self.client.get('/api/bootstrap',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/recording/start',headers={'Origin':'https://evil.example',**self.headers},json={}).status_code,403)

    def test_settings_never_return_secrets(self):
        response=self.client.get('/api/status',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('OPENAI_API_KEY',response.text)
        self.assertNotIn('NOTION_TOKEN',response.text)

    def test_validation_error_does_not_echo_credentials(self):
        secret='sk-'+'x'*1001
        response=self.client.put('/api/settings',headers=self.headers,json={'openai_key':secret})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(secret,response.text)

    def test_edit_search_and_exports(self):
        m=store.create('API 테스트','lecture')
        store.update(m['id'],status='complete',summary='요약')
        r=self.client.patch('/api/meetings/'+m['id'],headers=self.headers,json={'title':'검색 가능한 제목','notes':'본문 확인','tags':'검증','favorite':True})
        self.assertEqual(r.status_code,200)
        self.assertTrue(self.client.get('/api/meetings?q=본문&favorite=true',headers=self.headers).json())
        for kind in ('md','txt','json'):
            self.assertEqual(self.client.get(f'/api/meetings/{m["id"]}/export/{kind}',headers=self.headers).status_code,200)

    def test_no_arbitrary_fields_or_executable_open(self):
        m=store.create('검증','meeting')
        r=self.client.patch('/api/meetings/'+m['id'],headers=self.headers,json={'folder':'../../elsewhere'})
        self.assertEqual(r.status_code,422)
        store.update(m['id'],video_path='C:\\Windows\\System32\\cmd.exe')
        self.assertEqual(self.client.post(f'/api/meetings/{m["id"]}/open-video',headers=self.headers).status_code,400)

    def test_regeneration_backs_up_and_does_not_duplicate_transcription(self):
        m=store.create('기존 요약','lecture')
        store.update(m['id'],status='complete',summary='사용자가 편집한 요약',notes='유지할 메모',cleaned=1)
        response=self.client.post(f'/api/meetings/{m["id"]}/regenerate',headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(store.meeting(m['id'])['status'],'processing')
        self.assertEqual(store.meeting(m['id'])['notes'],'유지할 메모')
        self.assertIn('사용자가 편집한 요약',next(store.folder(m['id']).glob('summary-backup-*.json')).read_text('utf-8'))
        self.assertEqual(self.client.post(f'/api/meetings/{m["id"]}/regenerate',headers=self.headers).status_code,400)


if __name__=='__main__':
    unittest.main()
