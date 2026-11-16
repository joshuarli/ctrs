import json
import unittest
from unittest.mock import Mock, patch

import runner


class CacheAccountingTests(unittest.TestCase):
    def snapshot(self, payload):
        response = Mock(status=200)
        response.read.return_value = json.dumps(payload).encode()
        with patch('http.client.HTTPConnection.request'), patch('http.client.HTTPConnection.getresponse', return_value=response):
            return runner.Engine('orbstack', 'cache-test').system_df()

    def test_missing_or_invalid_entry_size_never_becomes_zero(self):
        for entry in ({}, {'Size': None}, {'Size': -1}, {'Size': False}):
            with self.subTest(entry=entry):
                snapshot = self.snapshot({'BuildCache': [entry]})
                self.assertEqual(snapshot['build_cache_entries'], 1)
                self.assertNotIn('build_cache_size_bytes', snapshot)
        self.assertIsNone(self.snapshot({'BuildCache': []}))
        self.assertIsNone(self.snapshot({}))

    def test_known_sizes_sum_but_one_unknown_invalidates_total(self):
        self.assertEqual(self.snapshot({'BuildCache': [{'Size': 100}, {'Size': 0}]}),
                         dict(build_cache_entries=2, build_cache_size_bytes=100))
        self.assertNotIn('build_cache_size_bytes', self.snapshot({'BuildCache': [{'Size': 100}, {}]}))
