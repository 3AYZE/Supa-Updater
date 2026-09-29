"""SupaUpdater: conservative Windows registry + WinGet discovery/update engine."""
from __future__ import annotations
import json, logging, os, re, shutil, subprocess, sys, threading, time
from dataclasses import dataclass, asdict
from pathlib import Path

APP_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SupaUpdater'
APP_DIR.mkdir(parents=True, exist_ok=True)
LOG = APP_DIR / 'supaupdater.log'
logging.basicConfig(filename=LOG, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

@dataclass
class App:
    name: str
    installed: str = ''
    available: str = ''
    package_id: str = ''
    source: str = ''
    publisher: str = ''
    location: str = ''
    status: str = 'Installed (update unknown)'


def registry_apps():
    if sys.platform != 'win32': return []
    import winreg
    paths = [r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
             r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall']
    found = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in paths:
            try: root = winreg.OpenKey(hive, path)
            except OSError: continue
            with root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        key = winreg.OpenKey(root, winreg.EnumKey(root, i))
                        with key:
                            def val(k):
                                try: return str(winreg.QueryValueEx(key,k)[0])
                                except OSError: return ''
                            name = val('DisplayName')
                            if name and not val('SystemComponent') == '1':
                                found.append(App(name=name, installed=val('DisplayVersion'),publisher=val('Publisher'),location=val('InstallLocation')))
                    except OSError: continue
    return found


def parse_winget_table(output):
    """Parse winget's column-aligned human output; refuse ambiguous or truncated rows."""
    lines = output.splitlines()
    header = next((i for i,s in enumerate(lines) if re.search(r'^Name\s+Id\s+Version\s+Available\s+Source\s*$', s)), None)
    if header is None: return []
    h = lines[header]
    positions = [h.index(c) for c in ('Name','Id','Version','Available','Source')]
    result=[]
    for line in lines[header+1:]:
        if not line.strip() or re.match(r'^[-\s]+$',line): continue
        cols = [line[positions[i]:positions[i+1]].strip() if i<4 else line[positions[i]:].strip() for i in range(5)]
        name,pid,installed,available,source=cols
        if not (name and pid and installed and available and source): continue
        if '…' in pid or '...' in pid or '…' in name: continue
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+\-]*',pid): continue
        result.append(App(name,installed,available,pid,source,status='Update available'))
    return result


def winget_path():
    return shutil.which('winget') if sys.platform=='win32' else None


def winget_updates(timeout=100):
    exe=winget_path()
    if not exe: return [], 'WinGet not found. Install Microsoft App Installer or enable its app execution alias.'
    try:
        p=subprocess.run([exe,'upgrade','--disable-interactivity'],capture_output=True,text=True,errors='replace',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except (OSError,subprocess.TimeoutExpired) as e:
        logging.exception('WinGet scan failed')
        return [],f'WinGet scan failed: {e}'
    rows=parse_winget_table(p.stdout)
    logging.info('WinGet scan exit=%s rows=%s stdout=%s stderr=%s', p.returncode, len(rows), p.stdout[-5000:], p.stderr[-2500:])
    if p.returncode and not rows: return [],'WinGet could not return a usable update list. Check the log and run winget upgrade manually.'
    if not rows and 'No installed package' not in p.stdout and 'No applicable update' not in p.stdout:
        return [],'WinGet returned no parseable updates; check the log or run winget upgrade manually.'
    return rows,''


def inventory():
    """Registry inventory is informational; only WinGet package IDs are installable."""
    registry=registry_apps()
    updates,error=winget_updates()
    return registry, updates, error


def check_package_update(app: App, timeout=100):
    """Re-query this exact package. Returns (state, message), never guesses from an empty parse."""
    exe = winget_path()
    if not exe:
        return 'unknown', 'WinGet is unavailable.'
    cmd = [exe, 'upgrade', '--id', app.package_id, '--exact', '--source', app.source,
           '--disable-interactivity']
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.exception('Verification failed for %s', app.package_id)
        return 'unknown', str(exc)
    output = (p.stdout + '\n' + p.stderr).strip()
    logging.info('Verification for %s: exit=%s output=%s', app.package_id, p.returncode, output[-2400:])
    rows = parse_winget_table(p.stdout)
    if any(row.package_id.casefold() == app.package_id.casefold() and
           row.source.casefold() == app.source.casefold() for row in rows):
        return 'still_available', 'WinGet still offers an update for this package.'
    if ('No available upgrade found' in output or 'No newer package versions are available' in output
            or 'No applicable update found' in output or 'No installed package found matching input criteria' in output):
        if 'No installed package found matching input criteria' in output:
            return 'unknown', 'WinGet no longer recognizes this installation.'
        return 'up_to_date', 'WinGet reports no further upgrade available.'
    return 'unknown', f'Unable to verify update (exit {p.returncode}).'


def update_one(app: App, confirm: bool=False, timeout=1800, verify=True):
    if not confirm:
        return False, 'Dry run: no changes made.'
    if not (app.package_id and app.source and app.status == 'Update available'):
        return False, 'Unverified package; installation blocked.'
    if app.source not in ('winget', 'msstore'):
        return False, 'Unsupported or unverified package source.'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+\-]*', app.package_id):
        return False, 'Invalid package identifier.'
    exe = winget_path()
    if not exe:
        return False, 'WinGet unavailable.'
    cmd = [exe, 'upgrade', '--id', app.package_id, '--exact', '--source', app.source,
           '--disable-interactivity', '--accept-package-agreements', '--accept-source-agreements']
    started = time.monotonic()
    logging.info('Starting verified catalog update: %s source=%s installed=%s target=%s',
                 app.package_id, app.source, app.installed, app.available)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.exception('Update failed: %s', app.package_id)
        return False, f'Installer did not finish: {exc}'
    output = (p.stdout + '\n' + p.stderr).strip()
    logging.info('Update finished: %s exit=%s duration=%.1fs output=%s',
                 app.package_id, p.returncode, time.monotonic()-started, output[-5000:])
    if p.returncode:
        if 'No available upgrade found' in output or 'No newer package versions are available' in output:
            return True, 'Already up to date according to WinGet (no installation needed).'
        return False, f'Installer returned code {p.returncode}. Check Activity and the log.'
    if not verify:
        return True, 'Installer exited successfully; verification not performed.'
    state, detail = check_package_update(app)
    if state == 'up_to_date':
        return True, 'Up to date according to WinGet; installed target version not independently confirmed.' 
    if state == 'still_available':
        return False, 'Unverified: WinGet still offers this update after installation.'
    return False, 'Installer exited successfully, but version could not be verified: ' + detail