import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('playground', Path(__file__).parents[1] / 'server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeManager:
    def __init__(self, user_id):
        self.user_id = user_id
        self.mode = 'menu'

    async def send_message(self, message):
        if message == 'fail':
            raise RuntimeError('simulated upstream failure')
        self.mode = 'puzzle' if message == 'puzzle' else self.mode
        if message == 'quit':
            self.mode = 'closed'
        payload = {'message': message, 'mode': self.mode, 'action': 'chat', 'image': None}
        class Reply:
            def model_dump(self, **kwargs):
                return payload
        return Reply()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = module.create_server(0, FakeManager)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.server.agent_loop.call_soon_threadsafe(cls.server.agent_loop.stop)
        cls.server.loop_thread.join()
        cls.server.agent_loop.close()

    def post(self, path, data, origin=None):
        request = Request(self.base + '/api/' + path, data=json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin or self.base})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_session_keeps_puzzle_mode_and_isolates_conversations(self):
        status, first = self.post('session', {})
        self.assertEqual(status, 201)
        _, second = self.post('session', {})
        self.assertNotEqual(first['session_id'], second['session_id'])
        self.post('message', {**first, 'message': 'puzzle'})
        _, followup = self.post('message', {**first, 'message': 'hint'})
        self.assertEqual(followup['mode'], 'puzzle')
        _, independent = self.post('message', {**second, 'message': 'hello'})
        self.assertEqual(independent['mode'], 'menu')
        self.assertEqual(self.post('end', first)[0], 200)
        self.assertEqual(self.post('message', {**first, 'message': 'hello'})[0], 404)

    def test_validation_and_origin(self):
        self.assertEqual(self.post('session', {}, 'https://example.com')[0], 403)
        _, session = self.post('session', {})
        for message in ['', None, 'x' * 4001]:
            self.assertEqual(self.post('message', {**session, 'message': message})[0], 400)
        self.assertEqual(self.post('message', {'session_id': 'missing', 'message': 'hi'})[0], 404)

    def test_upstream_error_does_not_break_conversation(self):
        _, session = self.post('session', {})
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.post('message', {**session, 'message': 'fail'})[0], 502)
        self.assertEqual(self.post('message', {**session, 'message': 'hello'})[0], 200)

    def test_frontend_and_health_are_served(self):
        for path in ['/', '/app.js', '/styles.css', '/api/health']:
            with urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
