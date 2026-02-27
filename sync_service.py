from __future__ import annotations
import os
import json
import time
from typing import Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


class SyncService:
    def __init__(self, base_url: str, token: str, user: str):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.user = user or "default"
        self._etag: Optional[str] = None

    def available(self) -> bool:
        return bool(self.base_url) and (requests is not None)

    def pull_to_file(self, file_path: str) -> bool:
        if not self.available():
            return False
        url = self.base_url + "/storage"
        headers = {}
        if self.token:
            headers["X-Token"] = self.token
        if self._etag:
            headers["If-None-Match"] = self._etag
        try:
            r = requests.get(url, params={"user": self.user}, headers=headers, timeout=15)
            if r.status_code == 304:
                return True
            if r.status_code != 200:
                return False
            et = r.headers.get("ETag", "")
            if et:
                self._etag = et.strip('"')
            # backup
            if os.path.exists(file_path):
                ts = time.strftime("%Y%m%d_%H%M%S")
                try:
                    import shutil
                    shutil.copy2(file_path, file_path + f".bak_{ts}")
                except Exception:
                    pass
            with open(file_path, "wb") as f:
                f.write(r.content)
            return True
        except Exception:
            return False

    def push_from_file(self, file_path: str) -> bool:
        if not self.available():
            return False
        if not os.path.exists(file_path):
            return False
        url = self.base_url + "/storage"
        headers = {}
        if self.token:
            headers["X-Token"] = self.token
        try:
            data = json.load(open(file_path, "r", encoding="utf-8"))
            r = requests.post(url, params={"user": self.user}, headers=headers, json=data, timeout=15)
            if r.status_code != 200:
                return False
            try:
                j = r.json()
                et = j.get("etag", "")
                if et:
                    self._etag = str(et)
            except Exception:
                pass
            return True
        except Exception:
            return False
