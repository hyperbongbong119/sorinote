# Deliberate allowlist: never bundle .env.local, data, logs or the workspace.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(['desktop.py'], pathex=[],
    binaries=[], datas=[('dist', 'dist')] + collect_data_files('webview'),
    hiddenimports=['uvicorn.logging','uvicorn.loops.auto','uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto','uvicorn.lifespan.on',
        'tests.test_engine','tests.test_provider','tests.test_api','tests.test_resilience'] + collect_submodules('pyaudiowpatch'),
    excludes=['PyQt5','PyQt6','PySide2','PySide6','IPython','matplotlib'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Sorinote',
    debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Sorinote')
