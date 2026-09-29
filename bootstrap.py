import base64
import hashlib
import json
import zlib
from pathlib import Path

encoded = Path("release-payload.b64").read_text(encoding="utf-8")
payload = zlib.decompress(base64.b64decode(encoded, validate=True))
expected = "fb6cdfd3b1ab46571d20201d51f9c870b03e76e3406544e29b2cf0f12f4e073c"
if hashlib.sha256(payload).hexdigest() != expected:
    raise ValueError("Release source payload digest mismatch")
files = json.loads(payload)
for name, content in files.items():
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not isinstance(content, str):
        raise ValueError("Invalid release source path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
Path("release-payload.b64").unlink()
Path("bootstrap.py").unlink()
