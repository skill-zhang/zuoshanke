"""检查各表数据量和状态"""
import sys, os
sys.path.insert(0, '/home/administrator/zuoshanke/backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
tables = [
    'projects', 'scenes', 'thinking_maps', 'think_nodes', 'cross_refs',
    'channels', 'messages', 'settings',
    'action_maps', 'action_nodes', 'action_edges', 'action_execution_logs',
    'priority_queues', 'reflect_timelines',
    'agent_memory', 'gateway_sessions', 'dialog_states',
    'zhu_agents', 'scene_assets', 'category_meta', 'project_outputs',
]

for t in tables:
    try:
        result = db.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
        count = result.scalar()
        print(f'  {t:25s} → {count} 行')
    except Exception as e:
        print(f'  {t:25s} → ERROR: {e}')

db.close()
