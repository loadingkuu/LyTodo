"""LyTodo 方案A 同步服务端（FastAPI）
特点：单文件(JSON)上传/下载，原子写入，token 鉴权，支持 ETag/If-None-Match。
运行：
  pip install fastapi uvicorn
  export LYTODO_DATA_DIR=/var/lib/lytodo
  export LYTODO_TOKEN=your_token_here
  uvicorn server_fastapi:app --host 0.0.0.0 --port 8080

建议：前面用 Nginx 反代 + HTTPS。
"""

import os, json, hashlib, tempfile
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse

app = FastAPI()

DATA_DIR = os.environ.get("LYTODO_DATA_DIR", "./lytodo_data")
TOKEN = os.environ.get("LYTODO_TOKEN", "")

os.makedirs(DATA_DIR, exist_ok=True)

def _path(user: str) -> str:
    safe = "".join(ch for ch in user if ch.isalnum() or ch in "-_") or "default"
    return os.path.join(DATA_DIR, f"{safe}.json")

def _etag_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _auth(x_token: str | None):
    if TOKEN and (x_token != TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")

@app.get("/storage")
def get_storage(user: str = "default", if_none_match: str | None = Header(default=None), x_token: str | None = Header(default=None)):
    _auth(x_token)
    p = _path(user)
    if not os.path.exists(p):
        return JSONResponse({"version": 0, "payload": None}, headers={"ETag": "0"})
    b = open(p, "rb").read()
    et = _etag_bytes(b)
    if if_none_match and if_none_match.strip('"') == et:
        return Response(status_code=304)
    return Response(content=b, media_type="application/json", headers={"ETag": et})

@app.post("/storage")
def put_storage(body: dict, user: str = "default", x_token: str | None = Header(default=None)):
    _auth(x_token)
    p = _path(user)
    b = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
    et = _etag_bytes(b)

    # atomic write
    fd, tmp = tempfile.mkstemp(prefix="lytodo_", suffix=".json", dir=DATA_DIR)
    os.close(fd)
    with open(tmp, "wb") as f:
        f.write(b)
    os.replace(tmp, p)

    return JSONResponse({"ok": True, "etag": et})
