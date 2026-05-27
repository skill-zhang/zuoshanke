"""验证 LLM mock 是否真的生效"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_helpers import fake_agent_loop_events, fake_thinking, fake_done_event
from fastapi.testclient import TestClient
from database import init_db
init_db()
from main import app

c = TestClient(app)

# 创建场景
r = c.post("/api/scenes", json={"name": "mock_verify", "category": "life"})
sid = r.json()["id"]
print(f"场景ID: {sid}")

# 验证 patch
import json, threading
with fake_agent_loop_events([
    fake_thinking("mock思考"),
    fake_done_event("mock回复"),
]):
    resp = c.post(f"/api/scenes/{sid}/stream",
                  json={"content": "测试mock", "channel": "chat"})
    print(f"HTTP状态: {resp.status_code}")
    
    events = []
    def read():
        for line in resp.iter_lines():
            if not line: continue
            t = line.decode() if isinstance(line, bytes) else line
            if t.startswith('data: '):
                events.append(json.loads(t[6:]))
    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(timeout=5)

print(f"收到 {len(events)} 个事件")
for e in events:
    tp = e.get("type", "?")
    if tp == "error":
        print(f"  ERROR: {e.get('message', '')[:100]}")
    elif tp in ("done", "user_msg"):
        print(f"  {tp}: {str(e.get('content', e.get('summary', '')))[:60]}")
    else:
        print(f"  {tp}")
