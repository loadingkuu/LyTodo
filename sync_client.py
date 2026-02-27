"""LyTodo 方案A 同步客户端（Windows/安卓都能照抄）
用法（Windows）：
  python sync_client.py pull --url http://your_server:8080 --token your_token
  python sync_client.py push --url http://your_server:8080 --token your_token

说明：
- pull：拉取服务器 storage.json 覆盖本地（会备份）
- push：把本地 storage.json 推到服务器
- 本脚本只依赖 requests：pip install requests
"""

import argparse, os, shutil, time, json
import requests

DEFAULT_FILE = "storage.json"

def backup(path: str):
    if os.path.exists(path):
        ts = time.strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path + f".bak_{ts}")

def pull(base_url: str, token: str, user: str, file_path: str):
    url = base_url.rstrip("/") + "/storage"
    headers = {"X-Token": token} if token else {}
    r = requests.get(url, params={"user": user}, headers=headers, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"pull failed: {r.status_code} {r.text}")
    backup(file_path)
    with open(file_path, "wb") as f:
        f.write(r.content)
    print("pulled ok")

def push(base_url: str, token: str, user: str, file_path: str):
    url = base_url.rstrip("/") + "/storage"
    if not os.path.exists(file_path):
        raise SystemExit(f"{file_path} not found")
    headers = {"X-Token": token} if token else {}
    data = json.load(open(file_path, "r", encoding="utf-8"))
    r = requests.post(url, params={"user": user}, headers=headers, json=data, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"push failed: {r.status_code} {r.text}")
    print("pushed ok, etag=", r.json().get("etag"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pull","push"])
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", default="")
    ap.add_argument("--user", default="default")
    ap.add_argument("--file", default=DEFAULT_FILE)
    args = ap.parse_args()
    if args.cmd == "pull":
        pull(args.url, args.token, args.user, args.file)
    else:
        push(args.url, args.token, args.user, args.file)

if __name__ == "__main__":
    main()
