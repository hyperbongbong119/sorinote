"""Personal Windows desktop entry point; no Python installation needed after freezing."""
import argparse
import ctypes
import json
import multiprocessing
import socket
import sys
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--soak-seconds', type=int)
    parser.add_argument('--port', type=int, default=18767)
    parser.add_argument('--home', help='External folder containing .env.local and data')
    args = parser.parse_args()
    if args.home:
        import os
        os.environ['SORINOTE_HOME'] = args.home
    if args.self_test:
        import os
        from pathlib import Path
        from tools.acceptance import run
        report = Path(os.getenv('SORINOTE_HOME') or Path(os.environ['LOCALAPPDATA']) / 'Sorinote') / 'verification.json'
        result = run(report)
        return 0 if result['passed'] else 1
    from backend.paths import HOME, prepare
    prepare()
    if args.soak_seconds:
        from tools.soak import run
        result = run(args.soak_seconds, HOME / 'verification-soak.json')
        return 0 if result['passed'] else 1
    log = (HOME / 'desktop.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log
    import uvicorn
    from backend.app import app, engine
    url = f'http://127.0.0.1:{args.port}'
    # Refuse unknown port occupants instead of loading their content into a native window.
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', args.port))
        sock.listen(128)
    except OSError:
        sock.close()
        raise RuntimeError('이미 실행 중이거나 포트를 사용할 수 없습니다. 기존 소리노트를 확인하세요.')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False, log_config=None))
    app.state.request_shutdown = lambda: setattr(server, 'should_exit', True)
    if args.headless:
        server.run(sockets=[sock])
        return 0
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    try:
        for _ in range(100):
            if server.started:
                break
            if not worker.is_alive():
                raise RuntimeError('저장소가 사용 중이거나 서버를 시작하지 못했습니다.')
            time.sleep(.1)
        if not server.started:
            raise RuntimeError('서버 준비 시간이 초과되었습니다.')
        import webview
        webview.settings['ALLOW_DOWNLOADS'] = True
        window = webview.create_window('소리노트', url, width=1240, height=820, min_size=(760, 560), confirm_close=True)

        def closing():
            if engine.capture.thread and engine.capture.thread.is_alive():
                ctypes.windll.user32.MessageBoxW(0, '녹음 종료 후 창을 닫아 주세요.', '소리노트', 0)
                return False
        window.events.closing += closing
        window.events.loaded += lambda: log.write('Desktop UI loaded\n')
        webview.start(gui='edgechromium', private_mode=True)
    finally:
        server.should_exit = True
        worker.join(timeout=8)
        sock.close()
    return 0


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not expose provider bodies or credentials through native error dialogs.
        ctypes.windll.user32.MessageBoxW(0, f'시작 실패 ({type(exc).__name__}). 소리노트가 이미 열려 있는지, WebView2가 설치되어 있는지 확인하세요.', '소리노트', 0)
        raise
