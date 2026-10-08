"""Exercise manager transitions without network calls or a real database."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from Simple_entertaining_agent import entertainment_manager as module
from Simple_entertaining_agent.cute_image_agent import ImageResult
from Simple_entertaining_agent.puzzle_agent import PuzzleReply


def routing_result(action, subject=None):
    """Build the structured routing result returned by the manager agent."""
    return SimpleNamespace(final_output=module.ManagerReply(
        message="Acknowledged", action=action, image_subject=subject,
    ))


def puzzle_result(status):
    """Build a specialist reply for one puzzle turn."""
    return SimpleNamespace(final_output=PuzzleReply(message=status, status=status))


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.patches = [
            patch.object(module, 'load_dotenv'),
            patch.dict(module.os.environ, {'OPENAI_API_KEY': 'test-key'}),
            patch.object(module, 'Runner'),
            patch.object(module, 'SQLiteSession'),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        module.Runner.run = AsyncMock()
        self.manager = module.EntertainmentManager('alice')

    async def test_puzzle_continuation_and_completion(self):
        module.Runner.run.side_effect = [routing_result('puzzle'), puzzle_result('playing'),
                                        puzzle_result('playing'), puzzle_result('solved'), routing_result('chat')]
        self.assertEqual((await self.manager.send_message('puzzle')).mode, 'puzzle')
        self.assertEqual((await self.manager.send_message('hint')).puzzle_status, 'playing')
        self.assertEqual((await self.manager.send_message('clock')).mode, 'menu')
        self.assertEqual((await self.manager.send_message('hello')).action, 'chat')
        calls = module.Runner.run.call_args_list
        self.assertEqual(calls[1].args[1], 'Start a new one-word puzzle.')
        self.assertEqual(calls[2].args[1], 'hint')
        self.assertEqual(calls[3].args[1], 'clock')
        module.SQLiteSession.assert_called_with('alice:puzzles', module.DB_PATH)
        self.assertEqual(module.SQLiteSession.return_value.close.call_count, 3)
        saved_reply = json.loads(calls[4].args[1][-2]['content'])
        self.assertEqual(saved_reply['puzzle_status'], 'solved')
        self.assertEqual(saved_reply['mode'], 'menu')

    async def test_menu_quit_and_empty_skip_api(self):
        self.assertEqual((await self.manager.send_message(' ')).mode, 'menu')
        module.Runner.run.side_effect = [routing_result('puzzle'), puzzle_result('playing')]
        await self.manager.send_message('puzzle')
        self.assertEqual((await self.manager.send_message('')).mode, 'puzzle')
        self.assertEqual((await self.manager.send_message('back')).mode, 'menu')
        self.assertEqual((await self.manager.send_message('STOP!')).mode, 'closed')
        self.assertEqual((await self.manager.send_message('joke')).mode, 'closed')
        self.assertEqual(module.Runner.run.await_count, 2)

    async def test_joke_fact_and_surprise(self):
        for action, task in [('joke', 'jokes'), ('fact', 'facts')]:
            module.Runner.run.side_effect = [routing_result(action), SimpleNamespace(final_output='content')]
            response = await self.manager.send_message(action)
            self.assertEqual(response.message, 'content')
            self.assertEqual(response.action, action)
            self.assertEqual(response.mode, 'menu')
            expected_prompt = 'Tell me a joke.' if action == 'joke' else 'Tell me a fun fact.'
            self.assertEqual(module.Runner.run.call_args.args[1], expected_prompt)
            module.SQLiteSession.assert_called_with('alice:' + task, module.DB_PATH)
        module.Runner.run.side_effect = [routing_result('surprise'), SimpleNamespace(final_output='surprise joke')]
        with patch.object(module.random, 'choice', return_value='joke'):
            self.assertEqual((await self.manager.send_message('surprise me')).action, 'joke')

    async def test_image_and_missing_image(self):
        image = ImageResult(title='Kitten', image_url='https://example.com/a.jpg',
                            source_url='https://example.com/source', caption='A kitten')
        module.Runner.run.side_effect = [routing_result('image', 'kitten'), routing_result('image')]
        with patch.object(module, 'CuteImage', AsyncMock(side_effect=[image, None])) as search:
            response = await self.manager.send_message('kitten')
            self.assertEqual(response.model_dump(mode='json')['image']['title'], 'Kitten')
            search.assert_awaited_with(user_id='alice', subject='kitten', hooks=ANY)
            missing_image_reply = await self.manager.send_message('image')
            self.assertIsNone(missing_image_reply.image)
            self.assertIn('No suitable image', missing_image_reply.message)
            search.assert_awaited_with(user_id='alice', subject='cute baby animal', hooks=ANY)

    async def test_failed_puzzle_start_closes_session_and_does_not_commit_mode(self):
        module.Runner.run.side_effect = [routing_result('puzzle'), RuntimeError('offline')]
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            await self.manager.send_message('puzzle')
        self.assertEqual(self.manager.mode, 'menu')
        module.SQLiteSession.return_value.close.assert_called_once()
        module.Runner.run.side_effect = [routing_result('chat')]
        await self.manager.send_message('hello')
        self.assertEqual(module.Runner.run.call_args.args[1], [{'role': 'user', 'content': 'hello'}])

    async def test_revealed_and_natural_language_quit(self):
        module.Runner.run.side_effect = [routing_result('puzzle'), puzzle_result('playing'),
                                        puzzle_result('revealed'), routing_result('quit')]
        await self.manager.send_message('puzzle')
        self.assertEqual((await self.manager.send_message('give up')).puzzle_status, 'revealed')
        self.assertEqual(self.manager.mode, 'menu')
        self.assertEqual((await self.manager.send_message('I want to leave')).mode, 'closed')

    async def test_validation_and_independent_instances(self):
        with self.assertRaises(ValueError):
            module.EntertainmentManager(' ')
        with self.assertRaises(ValueError):
            await self.manager.send_message(None)
        other = module.EntertainmentManager('bob')
        await self.manager.send_message('quit')
        self.assertEqual(other.mode, 'menu')

    async def test_overlapping_messages_wait_for_puzzle_to_start(self):
        """A hint must wait until the preceding request has started its puzzle."""
        puzzle_started = asyncio.Event()
        allow_puzzle_reply = asyncio.Event()
        hint_submitted = asyncio.Event()
        specialist_messages = []

        async def run_agent(agent, message, **kwargs):
            if isinstance(message, list):
                return routing_result('puzzle')
            specialist_messages.append(message)
            if message == 'Start a new one-word puzzle.':
                puzzle_started.set()
                await allow_puzzle_reply.wait()
            return puzzle_result('playing')

        async def request_hint():
            hint_submitted.set()
            return await self.manager.send_message('hint')

        module.Runner.run.side_effect = run_agent
        start_task = asyncio.create_task(self.manager.send_message('puzzle'))
        hint_task = None
        try:
            await asyncio.wait_for(puzzle_started.wait(), timeout=2)
            hint_task = asyncio.create_task(request_hint())
            await asyncio.wait_for(hint_submitted.wait(), timeout=2)
            self.assertFalse(hint_task.done())
            self.assertEqual(specialist_messages, ['Start a new one-word puzzle.'])

            allow_puzzle_reply.set()
            start_reply, hint_reply = await asyncio.wait_for(
                asyncio.gather(start_task, hint_task), timeout=2
            )
            self.assertEqual(start_reply.mode, 'puzzle')
            self.assertEqual(hint_reply.mode, 'puzzle')
            self.assertEqual(specialist_messages, ['Start a new one-word puzzle.', 'hint'])
            self.assertEqual(module.Runner.run.await_count, 3)
        finally:
            tasks = [task for task in (start_task, hint_task) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_failed_puzzle_followup_preserves_active_round(self):
        module.Runner.run.side_effect = [
            routing_result('puzzle'), puzzle_result('playing'),
            RuntimeError('offline'), puzzle_result('playing'),
        ]
        await self.manager.send_message('puzzle')
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            await self.manager.send_message('hint')
        self.assertEqual(self.manager.mode, 'puzzle')

        # A subsequent request can still acquire the lock and continue the round.
        reply = await self.manager.send_message('try another hint')
        self.assertEqual(reply.puzzle_status, 'playing')
        self.assertEqual(module.Runner.run.call_args.args[1], 'try another hint')
        self.assertEqual(module.SQLiteSession.return_value.close.call_count, 3)

    async def test_chat_reply_keeps_context_for_next_request(self):
        module.Runner.run.side_effect = [routing_result('chat'), routing_result('chat')]
        first_reply = await self.manager.send_message('  hello  ')
        await self.manager.send_message('what can you do?')

        conversation = module.Runner.run.call_args.args[1]
        self.assertEqual(conversation[0], {'role': 'user', 'content': 'hello'})
        self.assertEqual(json.loads(conversation[1]['content']), first_reply.model_dump(exclude={'trace'}))
        self.assertEqual(conversation[2]['content'], 'what can you do?')
        module.SQLiteSession.assert_not_called()

    async def test_temporary_history_reuses_memory_sessions_until_close(self):
        manager = module.EntertainmentManager('temporary-user', temporary=True)
        module.Runner.run.side_effect = [
            routing_result('puzzle'), puzzle_result('playing'), puzzle_result('solved'),
        ]
        await manager.send_message('puzzle')
        await manager.send_message('clock')
        module.SQLiteSession.assert_called_once_with('temporary-user:puzzles', ':memory:')
        module.SQLiteSession.return_value.close.assert_not_called()
        await manager.close()
        module.SQLiteSession.return_value.close.assert_called_once()
        self.assertEqual(manager._history, [])
        self.assertEqual(manager._sessions, {})

    async def test_reply_contains_final_trace_without_adding_it_to_model_history(self):
        module.Runner.run.side_effect = [routing_result('chat'), routing_result('chat')]
        reply = await self.manager.send_message('hello')
        self.assertEqual(reply.trace['routing_decision'], 'chat')
        self.assertIn('latency_ms', reply.trace)
        self.assertEqual(reply.trace, self.manager.last_trace)
        await self.manager.send_message('hello again')
        saved = json.loads(module.Runner.run.call_args.args[1][1]['content'])
        self.assertNotIn('trace', saved)

    async def test_failed_turn_exposes_finalized_trace_for_ui(self):
        module.Runner.run.side_effect = [routing_result('joke'), RuntimeError('offline')]
        with self.assertRaises(RuntimeError):
            await self.manager.send_message('joke')
        self.assertEqual(self.manager.last_trace['status'], 'error')
        self.assertEqual(self.manager.last_trace['selected_action'], 'joke')
        self.assertIn('latency_ms', self.manager.last_trace)


if __name__ == '__main__':
    unittest.main()
