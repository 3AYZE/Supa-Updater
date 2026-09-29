import unittest
from unittest.mock import patch
from engine import App, parse_winget_table, update_one, registry_apps

TABLE='''Name                      Id                        Version     Available   Source
--------------------------------------------------------------------------------
7-Zip 24.08               7zip.7zip                 24.08       25.01       winget
Visual Studio Code        Microsoft.VisualStudioCode 1.95        1.96        winget
'''
class EngineTests(unittest.TestCase):
    def test_parse(self):
        rows=parse_winget_table(TABLE)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0].package_id,'7zip.7zip')
    def test_no_header_fails_closed(self):
        self.assertEqual(parse_winget_table('No upgrades available'),[])
    def test_truncated_id_rejected(self):
        self.assertEqual(parse_winget_table(TABLE.replace('7zip.7zip','7zip.7…  ')),[parse_winget_table(TABLE)[1]])
    def test_dry_run(self):
        self.assertFalse(update_one(App('7-Zip',package_id='7zip.7zip',source='winget',status='Update available'))[0])
    def test_unverified_rejected(self):
        self.assertFalse(update_one(App('Unknown'),confirm=True)[0])
    def test_nonwindows_registry_empty(self):
        with patch('engine.sys.platform','linux'):self.assertEqual(registry_apps(),[])
if __name__=='__main__':unittest.main()