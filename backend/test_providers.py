"""验证 Provider + Model 表创建和种子数据"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

os.environ["DEEPSEEK_API_KEY"] = "sk-test-key-123"
os.environ["ZUOSHANKE_REBUILD_DB"] = "1"

from database import init_db, SessionLocal
from models import AiProvider, AiModel

init_db()

db = SessionLocal()
try:
    providers = db.query(AiProvider).all()
    print(f"Providers: {len(providers)}")
    for p in providers:
        models = db.query(AiModel).filter(AiModel.provider_id == p.id).order_by(AiModel.sort_order).all()
        print(f"  {p.name} ({p.id}): {p.base_url}")
        print(f"    api_key={'***' if p.api_key else '(empty)'}")
        print(f"    type={p.provider_type}, active={p.is_active}")
        print(f"    models={len(models)}:")
        for m in models:
            caps = []
            if m.vision: caps.append("🖼vis")
            if m.function_calling: caps.append("🔧fc")
            print(f"      [{m.sort_order}] {m.name} T={m.temperature} ctx={m.context_length} tok={m.max_tokens} {' '.join(caps)}")
finally:
    db.close()
