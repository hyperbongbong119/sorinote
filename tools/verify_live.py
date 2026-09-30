"""Explicit live smoke test: only a supplied synthetic audio fixture, never system audio."""
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.services import AIService, safe_error, secrets

settings={'stt_model':'gpt-4o-transcribe','summary_model':'gpt-5.6-luna','language':'en','glossary':''}
ai=AIService()
stage='transcription'
try:
    text=ai.transcribe(sys.argv[1],'',settings)
    print(json.dumps({'synthetic_transcript':text},ensure_ascii=True))
    assert text.strip(), 'empty transcript'
    assert 'monday' in text.lower() and 'budget' in text.lower(), 'Synthetic audio content was not recognized'
    stage='state'
    state,usage=ai.state({},[{'seq':1,'start':0,'text':text}],settings)
    stage='summary'
    summary,usage=ai.summarize({'title':'Synthetic smoke test','template':'meeting','state':json.dumps(state)},settings)
    assert summary.strip(), 'empty summary'
    print(json.dumps({'transcription':'passed','state':'passed','summary':'passed',
                      'transcript_characters':len(text),'summary_characters':len(summary)}))
except Exception as exc:
    body=getattr(exc,'body',{}) or {}
    message=body.get('message','')
    for secret in secrets().values():
        if secret:
            message=message.replace(secret,'[redacted]')
    print(json.dumps({'result':'failed','stage':stage,'reason':safe_error(exc),
                      'code':body.get('code'),'param':body.get('param'),'type':body.get('type'),'message':message[:500]}))
    sys.exit(1)
