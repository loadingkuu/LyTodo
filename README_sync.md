# LyTodo 同步（方案A：最快、稳、最省事）

## 目标
- Windows 现在就能用
- 未来安卓 App 直接复用同一套接口
- 同步对象只有一个：`storage.json`

---

## 服务端（Linux）
### 1) 安装
```bash
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn
```

### 2) 运行
```bash
export LYTODO_DATA_DIR=/var/lib/lytodo
export LYTODO_TOKEN=your_token_here
mkdir -p /var/lib/lytodo

uvicorn server_fastapi:app --host 0.0.0.0 --port 8080
```

### 3) 防火墙放行端口/或 Nginx 反代
强烈建议用 Nginx + HTTPS（域名证书），然后只暴露 443。

---

## 客户端（Windows）
### 拉取
```bash
pip install requests
python sync_client.py pull --url https://your-domain.com --token your_token_here
```

### 推送
```bash
python sync_client.py push --url https://your-domain.com --token your_token_here
```

---

## 冲突处理（简单但稳）
当前策略：你可以先 `pull` 再打开软件；关闭软件后 `push`。
如果你需要“自动合并”，下一步我可以按 `Task.updated_at` 做逐条合并（安卓也一致）。
