"""Local, atomic preferences and append-only update history."""
import json, os, tempfile
from pathlib import Path
from engine import APP_DIR
PREFS=APP_DIR/'settings.json'
HISTORY=APP_DIR/'history.jsonl'

def load_settings():
    try:
        data=json.loads(PREFS.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError): return {}

def save_settings(data):
    APP_DIR.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.settings-',suffix='.json',dir=APP_DIR)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(name,PREFS)
    finally:
        if os.path.exists(name):os.unlink(name)

def record_result(record):
    APP_DIR.mkdir(parents=True,exist_ok=True)
    with HISTORY.open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')

def read_history(limit=300):
    if not HISTORY.exists():return []
    with HISTORY.open(encoding='utf-8') as f: lines=f.readlines()[-limit:]
    records=[]
    for line in reversed(lines):
        try: records.append(json.loads(line))
        except ValueError:continue
    return records