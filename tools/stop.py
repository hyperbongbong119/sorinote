import json
import urllib.request

url='http://127.0.0.1:18765'
try:
    with urllib.request.urlopen(url+'/api/bootstrap',timeout=3) as r:
        bootstrap=json.load(r)
    if bootstrap.get('app')!='sorinote':
        raise RuntimeError('Not Sorinote')
    req=urllib.request.Request(url+'/api/shutdown',method='POST',headers={'X-Sorinote-Token':bootstrap['token']})
    with urllib.request.urlopen(req,timeout=10) as r:
        json.load(r)
    print('Sorinote stopped. Local files are preserved.')
except Exception:
    print('Could not stop Sorinote. Finish recording first, or check whether it is running.')
    raise SystemExit(1)
