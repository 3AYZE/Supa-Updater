"""Detached helper: wait for the app to exit, then atomically replace staged source files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def apply_stage(stage, target, parent_pid, restart=True):
    stage, target = Path(stage).resolve(), Path(target).resolve()
    if not (stage / 'version.json').is_file() or not (target / 'app.pyw').is_file():
        raise ValueError('Invalid update directory')
    names = [p.name for p in stage.iterdir() if p.is_file()]
    if not {'app.pyw', 'engine.py', 'self_update.py', 'update_helper.py', 'version.json'} <= set(names):
        raise ValueError('Incomplete staged update')
    backup = target / '.previous-update'
    backup.mkdir(exist_ok=True)
    replaced = []
    try:
        for name in names:
            src, dest = stage / name, target / name
            previous = backup / name
            if dest.exists():
                shutil.copy2(dest, previous)
            else:
                previous.unlink(missing_ok=True)
            os.replace(src, dest)
            replaced.append(name)
    except Exception:
        for name in reversed(replaced):
            previous = backup / name
            if previous.exists():
                os.replace(previous, target / name)
            else:
                (target / name).unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if restart:
        python = sys.executable
        subprocess.Popen([python, str(target / 'app.pyw')], cwd=str(target), close_fds=True)


def main():
    stage, target, pid = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            result = kernel.WaitForSingleObject(handle, 120000)
            kernel.CloseHandle(handle)
            if result != 0:
                raise TimeoutError('Main application did not exit')
    else:
        raise RuntimeError('Self-update helper only runs on Windows')
    apply_stage(stage, target, pid)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        location = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'SupaUpdater'
        location.mkdir(parents=True, exist_ok=True)
        (location / 'self-update-error.log').write_text(str(exc), encoding='utf-8')
        raise