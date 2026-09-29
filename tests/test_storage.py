import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
import storage
class StorageTests(unittest.TestCase):
 def test_preferences_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(storage,'APP_DIR',Path(d)),patch.object(storage,'PREFS',Path(d)/'settings.json'):
    storage.save_settings({'repository':'example/repo'});self.assertEqual(storage.load_settings()['repository'],'example/repo')
 def test_history_roundtrip(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(storage,'APP_DIR',Path(d)),patch.object(storage,'HISTORY',Path(d)/'history.jsonl'):
    storage.record_result({'name':'Example','result':'failed'});self.assertEqual(storage.read_history()[0]['result'],'failed')