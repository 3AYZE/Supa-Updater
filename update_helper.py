"""Detached SupaUpdater update helper."""
import os
from pathlib import Path
import shutil,subprocess,sys,time

def apply_stage(stage,target,parent_pid,restart=True):
    stage,target=Path(stage).resolve(),Path(target).resolve()
    if not (stage/'version.json').is_file() or not (target/'app.pyw').is_file(): raise ValueError('Invalid update directory')
    names=[p.name for p in stage.iterdir() if p.is_file()]
    if not {'app.pyw','engine.py','self_update.py','update_helper.py','version.json'}<=set(names): raise ValueError('Incomplete staged update')
    backup=target/'.previous-update'; backup.mkdir(exist_ok=True); replaced=[]
    try:
        for name in names:
            src,dest=stage/name,target/name; previous=backup/name
            if dest.exists(): shutil.copy2(dest,previous)
            else: previous.unlink(missing_ok=True)
            os.replace(src,dest); replaced.append(name)
    except Exception:
        for name in reversed(replaced):
            previous=backup/name
            if previous.exists(): os.replace(previous,target/name)
            else: (target/name).unlink(missing_ok=True)
        raise
    finally: shutil.rmtree(stage,ignore_errors=True)
    if restart: subprocess.Popen([sys.executable,str(target/'app.pyw')],cwd=str(target),close_fds=True)

def apply_executable(stage,target,parent_pid,restart=True):
    stage,target=Path(stage).resolve(),Path(target).resolve(); incoming=stage/'SupaUpdater.exe'
    if not incoming.is_file() or target.name.lower()!='supaupdater.exe': raise ValueError('Invalid executable update target')
    backup=target.with_suffix('.previous.exe')
    for attempt in range(20):
        try:
            if target.exists(): shutil.copy2(target,backup)
            os.replace(incoming,target); break
        except PermissionError:
            if attempt==19: raise
            time.sleep(1)
    shutil.rmtree(stage,ignore_errors=True)
    if restart:
        try: subprocess.Popen([str(target)],cwd=str(target.parent),close_fds=True)
        except Exception:
            if backup.exists(): shutil.copy2(backup,target)
            raise

def uninstall_application(target,parent_pid):
    target=Path(target).resolve()
    if target.name.lower()!='supaupdater.exe': raise ValueError('Invalid SupaUpdater uninstall target')
    parent=target.parent
    for attempt in range(20):
        try:
            target.unlink(missing_ok=True)
            break
        except PermissionError:
            if attempt==19: raise
            time.sleep(1)
    for name in ('SupaUpdaterUpdateHelper.exe','SupaUpdater.previous.exe'):
        path=parent/name
        if path.name.lower()!='supaupdaterupdatehelper.exe':
            path.unlink(missing_ok=True)
    # The helper cannot delete its own executable while running. Schedule that
    # final cleanup through cmd after this process exits.
    helper=parent/'SupaUpdaterUpdateHelper.exe'
    if helper.exists():
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        subprocess.Popen(['cmd.exe','/d','/c','ping 127.0.0.1 -n 3 >nul & del /f /q "'+str(helper)+'"'],creationflags=flags,close_fds=True)

def main():
    if os.name!='nt': raise RuntimeError('SupaUpdater helper only runs on Windows')
    uninstall_mode=len(sys.argv)>1 and sys.argv[1]=='--uninstall'
    if uninstall_mode:
        target,pid=sys.argv[2],int(sys.argv[3])
    else:
        stage,target,pid=sys.argv[1],sys.argv[2],int(sys.argv[3]); mode=sys.argv[4] if len(sys.argv)>4 else 'source'
    import ctypes
    kernel=ctypes.windll.kernel32; handle=kernel.OpenProcess(0x00100000,False,pid)
    if handle:
        result=kernel.WaitForSingleObject(handle,120000); kernel.CloseHandle(handle)
        if result!=0: raise TimeoutError('Main application did not exit')
    if uninstall_mode: uninstall_application(target,pid)
    else: apply_executable(stage,target,pid) if mode=='exe' else apply_stage(stage,target,pid)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        location=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SupaUpdater'; location.mkdir(parents=True,exist_ok=True)
        (location/'self-update-error.log').write_text(str(exc),encoding='utf-8'); raise
