"""Local React playground and HTTP bridge to the entertainment manager."""
import asyncio
import json
import logging
import sys
import threading
import uuid
from urllib.parse import urlparse, parse_qs
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from Simple_entertaining_agent.entertainment_manager import EntertainmentManager

def temporary_manager(user_id):
    return EntertainmentManager(user_id=user_id, temporary=True)


class Bridge:
    def __init__(self, factory=temporary_manager, grace=30):
        self.factory = factory
        self.sessions = {}
        self.messages = {}
        self.connections = {}
        self.expiry = {}
        self.grace = grace

    def schedule_expiry(self, token):
        old = self.expiry.pop(token, None)
        if old:
            old.cancel()
        self.expiry[token] = asyncio.get_running_loop().call_later(
            self.grace, lambda: asyncio.create_task(self.discard(token)))

    async def discard(self, token):
        timer = self.expiry.pop(token, None)
        if timer:
            timer.cancel()
        manager = self.sessions.pop(token, None)
        self.messages.pop(token, None)
        self.connections.pop(token, None)
        if manager:
            if hasattr(manager, 'close'):
                await manager.close()
            else:
                await manager.send_message('quit')

    async def connection(self, token, change):
        if token not in self.sessions:
            return False
        self.connections[token] = max(0, self.connections.get(token, 0) + change)
        if self.connections[token]:
            timer = self.expiry.pop(token, None)
            if timer:
                timer.cancel()
        else:
            self.schedule_expiry(token)
        return True

    async def close(self):
        for token in list(self.sessions):
            await self.discard(token)

    async def request(self, path, data):
        if path == '/api/session':
            if len(self.sessions) >= 100:
                return 503, {'error': 'Conversation limit reached. Restart the server.'}
            token = str(uuid.uuid4())
            self.sessions[token] = self.factory(user_id='ui-' + token)
            self.messages[token] = []
            self.schedule_expiry(token)
            return 201, {'session_id': token, 'mode': 'menu'}
        token = data.get('session_id')
        if not isinstance(token, str) or token not in self.sessions:
            return 404, {'error': 'Conversation expired. Start a new conversation.'}
        if path == '/api/message':
            message = data.get('message')
            if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                return 400, {'error': 'Enter a message between 1 and 4,000 characters.'}
            manager = self.sessions[token]
            try:
                response = await manager.send_message(message)
            except Exception:
                logging.exception('Entertainment request failed')
                payload = {
                    'error': 'The activity could not finish. Please try again.',
                    'message': 'The activity could not finish. Please try again.',
                    'mode': manager.mode, 'action': 'chat',
                    'trace': getattr(manager, 'last_trace', None),
                }
                if token in self.messages:
                    self.messages[token].extend([
                        {'role': 'user', 'message': message},
                        {**payload, 'role': 'assistant'},
                    ])
                return 502, payload
            payload = response.model_dump(mode='json')
            if token in self.messages:
                self.messages[token].extend([{'role': 'user', 'message': message}, {**payload, 'role': 'assistant'}])
            return 200, payload
        if path == '/api/resume':
            return 200, {'session_id': token, 'mode': self.sessions[token].mode, 'messages': self.messages[token]}
        if path == '/api/end':
            # Wait for any outstanding turn before removing its manager.
            await self.discard(token)
            return 200, {'ok': True}
        return 404, {'error': 'Unknown endpoint.'}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def end_headers(self):
        # This development UI changes without a build; always fetch fresh files.
        if not urlparse(self.path).path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def json_response(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/live':
            token = parse_qs(parsed.query).get('session_id', [''])[0]
            connected = asyncio.run_coroutine_threadsafe(self.server.bridge.connection(token, 1), self.server.agent_loop).result()
            if not connected:
                return self.json_response(404, {'error': 'Conversation expired.'})
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                while not self.server.stopping.is_set():
                    status, snapshot = asyncio.run_coroutine_threadsafe(
                        self.server.bridge.request('/api/resume', {'session_id': token}), self.server.agent_loop).result()
                    if status != 200:
                        break
                    self.wfile.write(('data: ' + json.dumps(snapshot) + '\n\n').encode())
                    self.wfile.flush()
                    self.server.stopping.wait(2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                asyncio.run_coroutine_threadsafe(self.server.bridge.connection(token, -1), self.server.agent_loop).result()
            return
        if self.path == '/api/health':
            return self.json_response(200, {'ok': True})
        super().do_GET()

    def do_POST(self):
        # Only this local UI can submit JSON requests; no cross-origin access.
        allowed = {f'http://localhost:{self.server.server_port}',
                   f'http://127.0.0.1:{self.server.server_port}'}
        if self.headers.get('Origin') not in allowed:
            return self.json_response(403, {'error': 'Use the local playground to send requests.'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_response(415, {'error': 'Expected JSON.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 20000:
                return self.json_response(413, {'error': 'Request too large or empty.'})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected object')
        except (ValueError, json.JSONDecodeError):
            return self.json_response(400, {'error': 'Invalid JSON request.'})
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.server.bridge.request(self.path, data), self.server.agent_loop)
            status, result = future.result()
            self.json_response(status, result)
        except Exception:
            logging.exception('Entertainment request failed')
            self.json_response(502, {'error': 'The agent could not complete this request. Check your API key, model, and connection in the server terminal, then try again.'})


class PlaygroundServer(ThreadingHTTPServer):
    def server_close(self):
        self.stopping.set()
        super().server_close()
        asyncio.run_coroutine_threadsafe(self.bridge.close(), self.agent_loop).result()


def create_server(port=8000, factory=temporary_manager):
    server = PlaygroundServer(('127.0.0.1', port), Handler)
    server.stopping = threading.Event()
    server.bridge = Bridge(factory)
    server.agent_loop = asyncio.new_event_loop()
    server.loop_thread = threading.Thread(target=server.agent_loop.run_forever, daemon=True)
    server.loop_thread.start()
    return server


if __name__ == '__main__':
    server = create_server()
    print('Entertainment playground: http://localhost:8000 (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.agent_loop.call_soon_threadsafe(server.agent_loop.stop)
        server.loop_thread.join()
        server.agent_loop.close()
