import unittest
from types import SimpleNamespace
from unittest.mock import patch
from engine import App, check_package_update, update_one

APP = App('CapCut', '5.0', '6.0', 'ByteDance.CapCut', 'winget', status='Update available')

class VerificationTests(unittest.TestCase):
    @patch('engine.winget_path', return_value='winget')
    @patch('engine.subprocess.run')
    def test_no_upgrade_after_install(self, run, _):
        run.side_effect = [SimpleNamespace(returncode=0,stdout='Successfully installed',stderr=''),
                           SimpleNamespace(returncode=0,stdout='No available upgrade found.\nNo newer package versions are available from the configured sources.',stderr='')]
        ok,msg=update_one(APP,confirm=True)
        self.assertTrue(ok)
        self.assertIn('Up to date',msg)
        self.assertEqual(run.call_count,2)
    @patch('engine.winget_path', return_value='winget')
    @patch('engine.subprocess.run')
    def test_failed_install_no_false_success(self, run, _):
        run.return_value=SimpleNamespace(returncode=1,stdout='',stderr='Installer failed')
        ok,msg=update_one(APP,confirm=True)
        self.assertFalse(ok)
        self.assertEqual(run.call_count,1)
    @patch('engine.winget_path', return_value='winget')
    @patch('engine.subprocess.run')
    def test_unrecognized_verification_fails_closed(self, run, _):
        run.side_effect = [SimpleNamespace(returncode=0,stdout='Installed',stderr=''),
                           SimpleNamespace(returncode=0,stdout='Unexpected output',stderr='')]
        ok,msg=update_one(APP,confirm=True)
        self.assertFalse(ok)
        self.assertIn('could not be verified',msg)
    @patch('engine.winget_path', return_value='winget')
    @patch('engine.subprocess.run')
    def test_already_up_to_date(self, run, _):
        run.return_value=SimpleNamespace(returncode=1,stdout='No available upgrade found.\nNo newer package versions are available',stderr='')
        ok,msg=update_one(APP,confirm=True)
        self.assertTrue(ok)
        self.assertIn('Already up to date',msg)
if __name__=='__main__': unittest.main()