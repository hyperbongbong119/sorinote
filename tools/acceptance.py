"""Same offline regression suite in source and in the packaged EXE."""
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path


def run(report):
    started=time.time()
    with tempfile.TemporaryDirectory(prefix='sorinote-verification-') as folder:
        # Set before any backend module import; real keys and recordings are excluded.
        os.environ['SORINOTE_HOME']=folder
        os.environ['SORINOTE_ENV_FILE']=str(Path(folder)/'.env.local')
        os.environ['SORINOTE_DATA_DIR']=str(Path(folder)/'data')
        for name in ('OPENAI_API_KEY','GROQ_API_KEY','GEMINI_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','NOTION_TOKEN'):
            os.environ.pop(name,None)
        suite=unittest.TestLoader().loadTestsFromNames(['tests.test_engine','tests.test_provider','tests.test_api','tests.test_resilience'])
        output=io.StringIO()
        result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
        payload={'passed':result.wasSuccessful(),'tests':result.testsRun,'seconds':round(time.time()-started,2),
                 'mode':'offline failure injection; no live Notion or real four-hour soak',
                 'failures':len(result.failures),'errors':len(result.errors),'details':output.getvalue()}
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    result=run(Path(sys.argv[1]) if len(sys.argv)>1 else Path('docs/verification-automated.json'))
    print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False))
    if not result['passed']:
        print(result['details'])
    raise SystemExit(0 if result['passed'] else 1)
