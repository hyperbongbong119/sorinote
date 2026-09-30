"""Check distribution contents without ever printing a credential."""
import json
import sys
import zipfile
from pathlib import Path
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
package=Path(sys.argv[1]) if len(sys.argv)>1 else root/'release'/'Sorinote-Windows.zip'
keys=[v.encode() for k,v in dotenv_values(root/'.env.local').items() if (k.endswith('_API_KEY') or k=='NOTION_TOKEN') and v and len(v)>16]
with zipfile.ZipFile(package) as archive:
    names=archive.namelist()
    assert any(n.endswith('Sorinote.exe') for n in names), 'Executable missing'
    assert 'install.cmd' in names and 'install.ps1' in names, 'Installer missing'
    assert '.env.example' in names, 'Environment template missing'
    for name in names:
        parts=Path(name).parts
        assert not any(part in ('.env.local','library.sqlite3','MeetingNotes') for part in parts), 'Private file included'
        content=archive.read(name)
        assert not any(key in content for key in keys), 'Credential material found in distribution'
print(json.dumps({'package':package.name,'files':len(names),'private_data_excluded':True,'credential_values_excluded':True,'bytes':package.stat().st_size}))
