"""Opt-in GitHub Releases self-update for source distributions of SupaUpdater."""
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import zipfile

VERSION = '1.3.0'
DEFAULT_REPO = '3AYZE/Supa-Updater'
MAX_ARCHIVE = 20 * 1024 * 1024
ALLOWED = {'app.pyw', 'engine.py', 'self_update.py', 'update_helper.py', 'README.md', 'storage.py', 'version.json', 'driver_scan.py', 'windows_updates.py'}


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Unsupported version format')
    return tuple(map(int, value.lstrip('v').split('.')))


def validate_repo(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo or ''):
        raise ValueError('Configure an owner/repository for SupaUpdater releases first')
    return repo


def check_release(repo, opener=urllib.request.urlopen):
    repo = validate_repo(repo)
    url = 'https://api.github.com/repos/' + repo + '/releases/latest'
    request = urllib.request.Request(url, headers={'Accept':'application/vnd.github+json', 'User-Agent':'SupaUpdater/' + VERSION})
    with opener(request, timeout=15) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Release metadata too large')
    release = json.loads(raw)
    latest = release['tag_name'].lstrip('v')
    if version_tuple(latest) <= version_tuple(VERSION):
        return None
    if release.get('draft') or release.get('prerelease'):
        return None
    expected_name = 'SupaUpdater-v' + latest + '-source.zip'
    assets = [a for a in release.get('assets', []) if a.get('name') == expected_name]
    if len(assets) != 1:
        raise ValueError('New release has no matching source update package')
    asset = assets[0]
    if not asset.get('digest','').startswith('sha256:'):
        raise ValueError('Release asset lacks GitHub SHA-256 digest; automatic installation blocked')
    expected_url = 'https://github.com/' + repo + '/releases/download/'
    if not asset.get('browser_download_url', '').startswith(expected_url):
        raise ValueError('Unexpected release asset URL')
    return {'version':latest, 'url':asset['browser_download_url'], 'size':asset.get('size', 0), 'release_url':release['html_url'], 'digest':asset['digest']}


def download_and_stage(release, directory, opener=urllib.request.urlopen, progress=None):
    """Download into a temporary directory and validate the complete archive before replacement."""
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', release.get('digest','')):
        raise ValueError('Release has no verifiable SHA-256 digest')
    if release['size'] > MAX_ARCHIVE:
        raise ValueError('Release package exceeds size limit')
    directory = Path(directory)
    stage = Path(tempfile.mkdtemp(prefix='supaupdater-update-'))
    try:
        request = urllib.request.Request(release['url'], headers={'User-Agent':'SupaUpdater/' + VERSION})
        with opener(request, timeout=45) as response:
            chunks = []
            received = 0
            declared = response.headers.get('Content-Length') if hasattr(response, 'headers') else None
            total = int(declared) if declared and declared.isdigit() else (release.get('size') or 0)
            while True:
                chunk = response.read(min(65536, MAX_ARCHIVE + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_ARCHIVE:
                    raise ValueError('Update archive exceeds size limit')
                chunks.append(chunk)
                if progress:
                    progress(received,total)
            data = b''.join(chunks)
            if response.geturl() != release['url'] and not response.geturl().startswith('https://release-assets.githubusercontent.com/'):
                raise ValueError('Unexpected download redirect')
        if len(data) > MAX_ARCHIVE:
            raise ValueError('Update archive exceeds size limit')
        import hashlib
        if hashlib.sha256(data).hexdigest().lower() != release['digest'][7:].lower():
            raise ValueError('Release checksum mismatch')
        archive = stage / 'release.zip'
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as z:
            files = {}
            for member in z.infolist():
                if member.is_dir():
                    continue
                parts = Path(member.filename.replace('\\', '/')).parts
                if len(parts) != 2 or parts[0] != 'SupaUpdater' or parts[1] not in ALLOWED or parts[1] in files:
                    raise ValueError('Unexpected archive contents')
                if member.file_size > 2 * 1024 * 1024 or member.compress_size == 0 and member.file_size:
                    raise ValueError('Invalid update member size')
                files[parts[1]] = z.read(member)
            if not {'app.pyw', 'engine.py', 'self_update.py', 'update_helper.py', 'version.json', 'driver_scan.py', 'windows_updates.py'} <= files.keys():
                raise ValueError('Required update files missing')
            metadata = json.loads(files['version.json'])
            if metadata.get('version') != release['version']:
                raise ValueError('Package version mismatch')
            for name, content in files.items():
                (stage / name).write_bytes(content)
        archive.unlink()
        return stage
    except Exception:
        import shutil
        shutil.rmtree(stage, ignore_errors=True)
        raise