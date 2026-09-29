import unittest
from pathlib import Path

class NavigationRegression(unittest.TestCase):
    def test_page_switch_does_not_hide_main(self):
        code=(Path(__file__).resolve().parent.parent / 'app.pyw').read_text()
        self.assertNotIn('self.progressbar.master.master',code)
        self.assertIn('self.progressbar.master)',code)