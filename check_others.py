import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from models import SessionLocal, Scene
db = SessionLocal()
scenes = db.query(Scene).filter(Scene.category == '其他').all()
print(f"Found {len(scenes)} scenes in '其他' category:")
for s in scenes:
    uctx = (s.user_context or '')[:100]
    print(f"  ID={s.id} name='{s.name}' icon={s.icon} user_context='{uctx}'")
db.close()
