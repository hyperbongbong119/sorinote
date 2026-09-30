"""Run the local-only server. No reload/multiple workers: one queue owner."""
if __name__ == '__main__':
    import uvicorn
    from backend.app import app
    server = uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18765,access_log=False))
    app.state.request_shutdown = lambda: setattr(server,'should_exit',True)
    server.run()
