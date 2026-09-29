import io
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from self_update import version_tuple, validate_repo, download_and_stage

class Response:
    def __init__(self, data, url):self.data=data;self.url=url
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):
        result=self.data[:n]
        self.data=self.data[n:]
        return result
    def geturl(self):return self.url

class Tests(unittest.TestCase):
    def test_versions(self):
        self.assertLess(version_tuple('0.3.0'),version_tuple('v0.4.0'))
        with self.assertRaises(ValueError):version_tuple('0.4.0-preview')
    def test_repo(self):
        self.assertEqual(validate_repo('owner/repo'),'owner/repo')
        with self.assertRaises(ValueError):validate_repo('https://invalid/path')
    def test_archive_rejects_traversal(self):
        url='https://github.com/owner/repo/releases/download/v0.5.0/SupaUpdater-v0.5.0-source.zip'
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            z.writestr('SupaUpdater/../evil.py','oops')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):download_and_stage({'url':url,'size':len(data.getvalue()),'version':'0.5.0','digest':'sha256:'+hashlib.sha256(data.getvalue()).hexdigest()},d,opener=lambda req,timeout:Response(data.getvalue(),url))
    def test_valid_archive(self):
        url='https://github.com/owner/repo/releases/download/v0.5.0/SupaUpdater-v0.5.0-source.zip'
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            for name in ['app.pyw','engine.py','self_update.py','update_helper.py','driver_scan.py','windows_updates.py']:
                z.writestr('SupaUpdater/'+name,'# test')
            z.writestr('SupaUpdater/version.json',json.dumps({'version':'0.5.0'}))
        with tempfile.TemporaryDirectory() as d:
            staged=download_and_stage({'url':url,'size':len(data.getvalue()),'version':'0.5.0','digest':'sha256:'+hashlib.sha256(data.getvalue()).hexdigest()},d,opener=lambda req,timeout:Response(data.getvalue(),url))
            self.assertTrue((staged/'app.pyw').exists())

if __name__=='__main__':unittest.main()