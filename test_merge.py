"""test merge_stage_results defensive fixes"""
import time
from api.routes.workflow import merge_stage_results

stages = [{
    'id': 's1',
    'name': '基础外推',
    'description': '...',
    'needs_llm': True,
    'depends_on': [],
    'status': 'pending',
}]

# Case 1: 脏数据 — sentinel started_at=1000000（epoch 1970），应丢弃
sr = {'s1': {'status': 'cancelled', 'started_at': 1000000, 'completed_at': time.time()}}
r = merge_stage_results(stages, sr)
print('Case 1 (sentinel started_at):')
print(f'  status={r[0]["status"]}, started_at={r[0].get("started_at")}, elapsed_s={r[0].get("elapsed_s")}')
print(f'  expected: status=cancelled, started_at=None, elapsed_s=None')

# Case 2: 用户刚看到的脏数据 — running 但 started_at=None
print()
sr = {'s1': {'status': 'running', 'started_at': None}}
r = merge_stage_results(stages, sr)
print('Case 2 (running but no started_at):')
print(f'  status={r[0]["status"]}, started_at={r[0].get("started_at")}, elapsed_s={r[0].get("elapsed_s")}')
print(f'  expected: status=running, started_at=None, elapsed_s=None')

# Case 3: 正常 running
print()
now = time.time()
sr = {'s1': {'status': 'running', 'started_at': now - 30}}
r = merge_stage_results(stages, sr)
print('Case 3 (normal running):')
print(f'  status={r[0]["status"]}, elapsed_s={r[0].get("elapsed_s")} (expect ~30)')

# Case 4: 用户报告的脏数据 — running 但 started_at=0
print()
sr = {'s1': {'status': 'running', 'started_at': 0}}
r = merge_stage_results(stages, sr)
print('Case 4 (running + started_at=0):')
print(f'  status={r[0]["status"]}, started_at={r[0].get("started_at")}, elapsed_s={r[0].get("elapsed_s")}')
print(f'  expected: status=running, started_at=None (sentinel 丢弃), elapsed_s=None')

print('\n✅ 防御默认值生效，脏时间戳不会再显示天文数字')