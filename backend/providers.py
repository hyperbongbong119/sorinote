"""Provider transport only. Prompts and meeting workflows stay in services/engine."""
from types import SimpleNamespace

import httpx
from openai import OpenAI

PROVIDERS = {
    'openai': {'name':'OpenAI','env':'OPENAI_API_KEY','url':'https://api.openai.com/v1'},
    'groq': {'name':'Groq','env':'GROQ_API_KEY','url':'https://api.groq.com/openai/v1'},
    'gemini': {'name':'Gemini','env':'GEMINI_API_KEY','url':'https://generativelanguage.googleapis.com/v1beta/openai/'},
    'anthropic': {'name':'Claude','env':'ANTHROPIC_API_KEY','url':'https://api.anthropic.com/v1'},
    'openrouter': {'name':'OpenRouter','env':'OPENROUTER_API_KEY','url':'https://openrouter.ai/api/v1'},
}
STT_MODELS = {'openai':['gpt-4o-transcribe','gpt-4o-mini-transcribe'],
              'groq':['whisper-large-v3-turbo','whisper-large-v3']}
AI_FIELDS = ('stt_provider','stt_model','summary_provider','summary_model')


def key_for(provider, keys):
    key = keys.get(PROVIDERS[provider]['env'],'')
    if not key:
        raise ValueError(f"{PROVIDERS[provider]['name']} API 키를 설정하세요.")
    return key


def client_for(provider, keys):
    # Explicit destinations prevent an environment base URL from leaking a different key.
    return OpenAI(api_key=key_for(provider, keys), base_url=PROVIDERS[provider]['url'],
                  timeout=90, max_retries=0)


def claude_headers(keys):
    return {'x-api-key':key_for('anthropic',keys),'anthropic-version':'2023-06-01'}


def generate_external(provider, keys, model, instructions, text, max_tokens, json_mode):
    if provider == 'anthropic':
        with httpx.Client(timeout=90) as client:
            response=client.post(PROVIDERS[provider]['url']+'/messages',headers=claude_headers(keys),json={
                'model':model,'max_tokens':max_tokens,'system':instructions,
                'messages':[{'role':'user','content':text}]})
            response.raise_for_status()
            body=response.json()
        if body.get('stop_reason')=='max_tokens':
            raise ValueError('Claude 응답 길이 제한에 도달했습니다.')
        output=''.join(part['text'] for part in body.get('content',[]) if part.get('type')=='text')
        usage=body.get('usage',{})
        return SimpleNamespace(output_text=output, usage=SimpleNamespace(
            input_tokens=usage.get('input_tokens',0)+usage.get('cache_read_input_tokens',0)+usage.get('cache_creation_input_tokens',0),
            output_tokens=usage.get('output_tokens',0)))
    options={}
    if json_mode:
        options['response_format']={'type':'json_object'}
    with client_for(provider, keys) as client:
        response=client.chat.completions.create(model=model,
            messages=[{'role':'system','content':instructions},{'role':'user','content':text}],
            max_tokens=max_tokens,**options)
    choice=response.choices[0]
    if choice.finish_reason not in ('stop',None):
        raise ValueError('모델 응답이 완성되지 않았습니다. 출력 한도와 모델 지원을 확인하세요.')
    usage=response.usage
    return SimpleNamespace(output_text=choice.message.content or '',usage=SimpleNamespace(
        input_tokens=usage.prompt_tokens if usage else 0, output_tokens=usage.completion_tokens if usage else 0))


def list_models(provider, keys):
    if provider=='anthropic':
        with httpx.Client(timeout=30) as client:
            response=client.get(PROVIDERS[provider]['url']+'/models',headers=claude_headers(keys),params={'limit':1000})
            response.raise_for_status()
            return sorted(m['id'] for m in response.json()['data'])
    if provider=='openrouter':
        # Its model catalog is public; separately authenticate before reporting key success.
        with httpx.Client(timeout=30) as client:
            response=client.get(PROVIDERS[provider]['url']+'/key',headers={'Authorization':'Bearer '+key_for(provider,keys)})
            response.raise_for_status()
    with client_for(provider,keys) as client:
        return sorted(m.id for m in client.models.list())
