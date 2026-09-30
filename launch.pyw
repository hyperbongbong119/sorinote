import json
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parent
url = 'http://127.0.0.1:18765'

def ready():
    try:
        with urllib.request.urlopen(url+'/api/bootstrap',timeout=1) as response:
            return json.load(response).get('app')=='sorinote'
    except Exception:
        return False

if not ready():
    (root/'data').mkdir(exist_ok=True)
    with (root/'data'/'server.log').open('a',encoding='utf-8') as log:
        subprocess.Popen([str(root/'.venv'/'Scripts'/'python.exe'),str(root/'run.py')],cwd=root,
                         stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(40):
        if ready():
            break
        time.sleep(.25)
if ready():
    webbrowser.open(url)
else:
    import ctypes
    ctypes.windll.user32.MessageBoxW(0,'앱을 시작하지 못했습니다. data/server.log를 확인하세요.','소리노트',0)
