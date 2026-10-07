import tempfile
import base64
import io
import json
import wave
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import httpx
from backend.providers import client_for, generate_external, list_models, transcribe_gemini, PROVIDERS

from backend.services import AIService
from backend.services import filter_citations


class ProviderContractTests(unittest.TestCase):
    def test_gemini_missing_source_links_retries_and_counts_usage(self):
        ai=AIService();ai.generate=MagicMock()
        fields=('topics','key_points','decisions','action_items','questions','important_terms','chapters')
        state={k:[] for k in fields};state['key_points']=['설명']
        cited={**state,'key_points':['설명 [원문](#chunk-2)']}
        ai.generate.side_effect=[SimpleNamespace(output_text=json.dumps(s),usage=SimpleNamespace(input_tokens=4,output_tokens=5)) for s in (state,cited)]
        result,usage=ai.state({},[{'seq':2,'start':0,'text':'설명'}],{'summary_provider':'gemini','summary_model':'fixture'})
        self.assertIn('#chunk-2',result['key_points'][0])
        self.assertEqual((usage.input_tokens,usage.output_tokens),(8,10))
        ai.generate.side_effect=None
        ai.generate.return_value=SimpleNamespace(output_text=json.dumps(state),usage=SimpleNamespace(input_tokens=1,output_tokens=1))
        with self.assertRaisesRegex(ValueError,'근거 링크'):
            ai.state({},[{'seq':2,'start':0,'text':'설명'}],{'summary_provider':'gemini','summary_model':'fixture'})

    def test_gemini_unavailable_model_has_safe_actionable_error(self):
        from backend.services import safe_error
        with patch('backend.providers.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value.status_code=404
            with self.assertRaises(ValueError) as raised:
                generate_external('gemini',{'GEMINI_API_KEY':'secret-fixture'},'gemini-2.5-flash-lite','한국어','input',100,False)
            self.assertIn('gemini-3.5-flash-lite',safe_error(raised.exception))
            self.assertNotIn('secret-fixture',safe_error(raised.exception))

    def test_gemini_native_summary_schema_and_bounded_retry(self):
        with patch('backend.providers.httpx.Client') as client:
            post=client.return_value.__enter__.return_value.post
            post.return_value.status_code=200
            post.return_value.json.side_effect=[
                {'candidates':[{'finishReason':'MAX_TOKENS'}],'usageMetadata':{'promptTokenCount':10,'thoughtsTokenCount':3}},
                {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}],'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':7}}]
            result=generate_external('gemini',{'GEMINI_API_KEY':'fixture'},'gemini-3.5-flash-lite','한국어 JSON','input',10000,True)
            self.assertEqual((result.usage.input_tokens,result.usage.output_tokens),(20,10))
            self.assertEqual([c.kwargs['json']['generationConfig']['maxOutputTokens'] for c in post.call_args_list],[10000,20000])
            payload=post.call_args.kwargs['json']
            self.assertEqual(payload['systemInstruction']['parts'][0]['text'],'한국어 JSON')
            self.assertIn('key_points',payload['generationConfig']['responseSchema']['required'])

    def test_gemini_english_translation_is_retried_then_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch('backend.providers.httpx.Client') as client:
            path=Path(d)/'audio.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16000)
            post=client.return_value.__enter__.return_value.post
            post.return_value.status_code=200
            post.return_value.json.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'transcript':'English translation '*20+'한'})}]}}]}
            with self.assertRaisesRegex(ValueError,'응답 언어'):
                transcribe_gemini(path,'bad English context',{'stt_model':'gemini-3.5-flash-lite','language':'ko','glossary':''},{'GEMINI_API_KEY':'fixture'})
            self.assertEqual(post.call_count,2)
            self.assertNotIn('bad English context',post.call_args.kwargs['json']['contents'][0]['parts'][0]['text'])

    def test_added_provider_auth_and_chat_transport(self):
        for provider in ('deepseek','mistral','xai'):
            with self.subTest(provider=provider), patch('backend.providers.OpenAI') as constructor:
                client_for(provider,{PROVIDERS[provider]['env']:'own-fixture','OPENAI_API_KEY':'wrong-key'})
                self.assertEqual(constructor.call_args.kwargs['api_key'],'own-fixture')
                self.assertEqual(constructor.call_args.kwargs['base_url'],PROVIDERS[provider]['url'])
                method=constructor.return_value.__enter__.return_value.chat.completions.create
                method.return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{}'))],usage=SimpleNamespace(prompt_tokens=11,completion_tokens=4))
                result=generate_external(provider,{PROVIDERS[provider]['env']:'own-fixture'},'deepseek-chat' if provider=='deepseek' else 'fixture','JSON only','input',10000,True)
                self.assertEqual(result.usage.output_tokens,4)
                self.assertEqual(method.call_args.kwargs['response_format'],{'type':'json_object'})
                self.assertEqual(method.call_args.kwargs['max_tokens'],8192 if provider=='deepseek' else 10000)

    def test_gemini_audio_is_mono_and_uses_only_gemini_key(self):
        with tempfile.TemporaryDirectory() as d, patch('backend.providers.httpx.Client') as client:
            path=Path(d)/'audio.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(b'\x01\x00'*96000)
            post=client.return_value.__enter__.return_value.post
            body={'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'hidden reasoning'},{'text':json.dumps({'transcript':'테스트 전사'})}]}}]}
            post.return_value.status_code=200
            post.return_value.json.return_value=body
            settings={'stt_model':'gemini-2.5-flash-lite','language':'ko','glossary':'용어'}
            self.assertEqual(transcribe_gemini(path,'이전 문맥',settings,{'GEMINI_API_KEY':'gemini-fixture','OPENAI_API_KEY':'wrong-key'}),'테스트 전사')
            self.assertIn('generativelanguage.googleapis.com',post.call_args.args[0])
            self.assertEqual(post.call_args.kwargs['headers'],{'x-goog-api-key':'gemini-fixture'})
            payload=post.call_args.kwargs['json']
            audio=payload['contents'][0]['parts'][1]['inlineData']
            with wave.open(io.BytesIO(base64.b64decode(audio['data'])),'rb') as wav:
                self.assertEqual((wav.getnchannels(),wav.getframerate(),wav.getnframes()),(1,16000,16000))
            for bad in ({'candidates':[]},{'candidates':[{'finishReason':'MAX_TOKENS'}]}, {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]}):
                post.return_value.json.return_value=bad
                with self.assertRaises(ValueError):transcribe_gemini(path,'',settings,{'GEMINI_API_KEY':'fixture'})

    def test_gemini_stt_routes_without_openai_transcription(self):
        with patch('backend.services.transcribe_gemini',return_value='speech') as transcribe, patch('backend.services.secrets',return_value={}), patch.object(AIService,'client') as client:
            self.assertEqual(AIService().transcribe('audio.wav','context',{'stt_provider':'gemini'}),'speech')
            transcribe.assert_called_once();client.assert_not_called()

    def test_truncated_json_retries_with_more_room_and_counts_all_usage(self):
        ai=AIService(); ai.client=MagicMock()
        method=ai.client.return_value.__enter__.return_value.responses.create
        valid='{"topics":[],"key_points":[],"decisions":[],"action_items":[],"questions":[],"important_terms":[],"chapters":[]}'
        method.side_effect=[
            SimpleNamespace(status='incomplete',incomplete_details=SimpleNamespace(reason='max_output_tokens'),output_text='{"topics":[',usage=SimpleNamespace(input_tokens=12,output_tokens=10)),
            SimpleNamespace(status='completed',incomplete_details=None,output_text=valid,usage=SimpleNamespace(input_tokens=12,output_tokens=20))]
        state,usage=ai.state({},[],{'summary_model':'fixture'})
        self.assertEqual(state['topics'],[])
        self.assertEqual([c.kwargs['max_output_tokens'] for c in method.call_args_list],[10000,20000])
        self.assertEqual((usage.input_tokens,usage.output_tokens),(24,30))

    def test_output_limit_is_bounded_and_partial_summary_is_rejected(self):
        ai=AIService(); ai.client=MagicMock()
        method=ai.client.return_value.__enter__.return_value.responses.create
        method.return_value=SimpleNamespace(status='incomplete',incomplete_details=SimpleNamespace(reason='max_output_tokens'),output_text='partial',usage=None)
        with self.assertRaises(ValueError):
            ai.summarize({'title':'test','template':'meeting','state':'{}'},{'summary_model':'fixture'})
        self.assertEqual(method.call_count,2)

    def test_provider_key_is_bound_to_its_endpoint(self):
        with patch('backend.providers.OpenAI') as constructor:
            client_for('groq',{'GROQ_API_KEY':'groq-fixture','OPENAI_API_KEY':'never-send-this'})
        self.assertEqual(constructor.call_args.kwargs['api_key'],'groq-fixture')
        self.assertEqual(constructor.call_args.kwargs['base_url'],'https://api.groq.com/openai/v1')

    def test_compatible_providers_normalize_usage_and_json_mode(self):
        for provider in ('groq','openrouter'):
            with self.subTest(provider=provider), patch('backend.providers.client_for') as factory:
                method=factory.return_value.__enter__.return_value.chat.completions.create
                method.return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"ok":true}'))],usage=SimpleNamespace(prompt_tokens=12,completion_tokens=5))
                result=generate_external(provider,{},'model','JSON only','input',100,True)
                self.assertEqual(result.usage.input_tokens,12)
                self.assertEqual(result.usage.output_tokens,5)
                self.assertEqual(method.call_args.kwargs['response_format'],{'type':'json_object'})
                self.assertEqual(factory.call_args.args[0],provider)

    def test_claude_uses_messages_and_its_own_header(self):
        with patch('backend.providers.httpx.Client') as client:
            post=client.return_value.__enter__.return_value.post
            post.return_value.json.return_value={'content':[{'type':'text','text':'summary'}],'stop_reason':'end_turn','usage':{'input_tokens':10,'cache_read_input_tokens':3,'output_tokens':4}}
            result=generate_external('anthropic',{'ANTHROPIC_API_KEY':'fixture','OPENAI_API_KEY':'not-anthropic'},'claude-haiku-4-5','instruction','input',100,False)
            self.assertEqual(post.call_args.args[0],'https://api.anthropic.com/v1/messages')
            self.assertEqual(post.call_args.kwargs['headers']['x-api-key'],'fixture')
            self.assertEqual(result.output_text,'summary')
            self.assertEqual(result.usage.input_tokens,13)

    def test_openrouter_public_catalog_does_not_imply_authenticated_key(self):
        with patch('backend.providers.httpx.Client') as client, patch('backend.providers.client_for') as factory:
            client.return_value.__enter__.return_value.get.return_value.raise_for_status.side_effect=httpx.HTTPStatusError('unauthorized',request=httpx.Request('GET','https://openrouter.ai/api/v1/key'),response=httpx.Response(401))
            with self.assertRaises(httpx.HTTPStatusError):
                list_models('openrouter',{'OPENROUTER_API_KEY':'invalid'})
            factory.assert_not_called()

    def test_groq_transcription_routes_separately_from_summary(self):
        ai=AIService();ai.client=MagicMock()
        ai.client.return_value.__enter__.return_value.audio.transcriptions.create.return_value.text='transcript'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'audio.wav';path.write_bytes(b'fixture')
            ai.transcribe(path,'',{'language':'ko','glossary':'','stt_provider':'groq','stt_model':'whisper-large-v3-turbo','summary_provider':'anthropic'})
        ai.client.assert_called_once_with('groq')

    def test_source_links_reject_unknown_ids(self):
        self.assertEqual(filter_citations('사실 [원문](#chunk-4) 거짓 [원문](#chunk-999)', {4}),
                         '사실 [원문](#chunk-4) 거짓 ')

    def test_summary_preserves_evidence_and_uses_topic_style(self):
        ai=AIService(); client=MagicMock(); ai.client=MagicMock(return_value=client)
        method=client.__enter__.return_value.responses.create
        method.return_value.output_text='### 개념\n- **자동화** [원문](#chunk-2) [원문](#chunk-9)'
        summary,_=ai.summarize({'title':'강의','template':'lecture','state':'{"key_points":["자동화 [원문](#chunk-2)"]}'},{'summary_model':'gpt-5.6-luna'})
        self.assertIn('#chunk-2',summary); self.assertNotIn('#chunk-9',summary)
        self.assertIn('Notion 스타일',method.call_args.kwargs['instructions'])

    def test_empty_context_is_omitted_from_transcription(self):
        ai=AIService()
        client=MagicMock()
        ai.client=MagicMock(return_value=client)
        method=client.__enter__.return_value.audio.transcriptions.create
        method.return_value.text='actual speech'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.wav';p.write_bytes(b'fixture')
            self.assertEqual(ai.transcribe(p,'',{'language':'','glossary':'','stt_model':'gpt-4o-transcribe'}),'actual speech')
            self.assertNotIn('prompt',method.call_args.kwargs)
            self.assertNotIn('language',method.call_args.kwargs)

    def test_json_mode_mentions_json_in_input(self):
        ai=AIService()
        client=MagicMock()
        ai.client=MagicMock(return_value=client)
        method=client.__enter__.return_value.responses.create
        method.return_value.output_text='{"topics":[],"key_points":[],"decisions":[],"action_items":[],"questions":[],"important_terms":[],"chapters":[]}'
        ai.state({},[],{'summary_model':'gpt-5.6-luna'})
        self.assertIn('json',method.call_args.kwargs['input'].lower())
