import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('queue', Path(__file__).resolve().parents[1] / 'scripts/buffer_queue.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

class QueueTests(unittest.TestCase):
    def test_drafts_are_interleaved(self):
        posts = q.drafts()
        self.assertEqual(len(posts), 120)
        self.assertEqual([p['key'] for p in posts[:3]], ['01A', '02A', '03A'])
        self.assertEqual(posts[24]['key'], '01B')

    def test_japan_nine_and_cutoff(self):
        for instant, day in [('2026-10-30T11:00:00+00:00', 31), ('2026-10-30T23:50:00+00:00', 1)]:
            slots = q.due_slots(dt.datetime.fromisoformat(instant))
            self.assertEqual(slots[0].day, day)
            self.assertTrue(all(t.hour == 0 for t in slots))
            self.assertEqual(len(slots), 7)

    def setup_run(self, state, posts, publish=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text(json.dumps(state))
            with patch.object(q, 'STATE', path), patch.object(q, 'channel', return_value={'id': 'x'}), patch.object(q, 'all_posts', return_value=posts), patch.object(q, 'checkpoint') as checkpoint, patch.object(q, 'api') as api:
                now = dt.datetime(2026, 10, 30, 11, tzinfo=dt.timezone.utc)
                q.run(publish, now)
                return api, checkpoint

    def test_preview_never_mutates(self):
        api, checkpoint = self.setup_run({'receipts': {}}, [])
        api.assert_not_called()
        checkpoint.assert_not_called()

    def test_pending_unknown_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'Uncertain'):
            self.setup_run({'receipts': {'01A': {'text': 'uncertain', 'status': 'pending'}}}, [], True)

    def test_full_queue_no_creation(self):
        posts = [{'id': str(i), 'text': str(i), 'dueAt': '2026-11-01T00:00:00Z', 'status': 'buffer'} for i in range(10)]
        api, _ = self.setup_run({'receipts': {}}, posts, True)
        api.assert_not_called()

    def test_intent_is_saved_before_creation_and_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text(json.dumps({'receipts': {}}))
            remote = []
            def save(state):
                path.write_text(json.dumps(state))
            def create(query, variables):
                payload = variables['input']
                persisted = json.loads(path.read_text())
                self.assertTrue(any(r['status'] == 'pending' and r['text'] == payload['text'] for r in persisted['receipts'].values()))
                post = dict(id=str(len(remote)), text=payload['text'], dueAt=payload['dueAt'], status='buffer')
                remote.append(post)
                return {'createPost': {'__typename': 'PostActionSuccess', 'post': post}}
            with patch.object(q, 'STATE', path), patch.object(q, 'channel', return_value={'id': 'x'}), patch.object(q, 'all_posts', side_effect=lambda c: list(remote)), patch.object(q, 'checkpoint', side_effect=save), patch.object(q, 'api', side_effect=create) as api:
                now = dt.datetime(2026, 10, 30, 11, tzinfo=dt.timezone.utc)
                q.run(True, now)
                self.assertEqual(len(remote), 7)
                q.run(True, now)
                self.assertEqual(api.call_count, 7)
                self.assertEqual(len(remote), 7)

    def test_account_switch_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'Channel changed'):
            self.setup_run({'receipts': {}, 'channel_id': 'other'}, [], True)

    def test_failed_post_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'publishing failed'):
            self.setup_run({'receipts': {'01A': {'id': '1', 'text': 'failed', 'status': 'scheduled'}}},
                           [{'id': '1', 'text': 'failed', 'status': 'error', 'dueAt': None}], True)

if __name__ == '__main__':
    unittest.main()
