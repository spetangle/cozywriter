"""清理 workflow_runs 里不一致的 stage 数据"""
import json
import sqlite3
import time

conn = sqlite3.connect('data/cozywriter.db')
cur = conn.cursor()

cur.execute('SELECT id, status, stage_results FROM workflow_runs')
runs = cur.fetchall()
fixed_count = 0
for run_id, run_status, sr_json in runs:
    if not sr_json:
        continue
    try:
        sr = json.loads(sr_json) if isinstance(sr_json, str) else sr_json
    except Exception:
        continue

    updated = False
    for sid, info in list(sr.items()):
        if not isinstance(info, dict):
            continue
        st = info.get('status')
        started = info.get('started_at')
        completed = info.get('completed_at')
        # 清掉 sentinel started_at
        if started is not None and started < 1_000_000_000:
            sr[sid] = {**info}
            sr[sid].pop('started_at', None)
            started = None
            updated = True
        # 终态缺 completed_at → 补成 now
        if st in ("ok", "user_filled", "skipped", "failed", "cancelled") and started and not completed:
            sr[sid]['completed_at'] = time.time()
            updated = True
        # running 状态超过 30 分钟 → 视为 orphaned（服务重启遗留），标 cancelled
        if st == "running" and started and (time.time() - started) > 1800:
            sr[sid] = {
                **info,
                'status': 'cancelled',
                'error': '服务重启/超时 (>30min 未完成)',
                'completed_at': time.time(),
            }
            updated = True
            print(f'  Run {run_id}: {sid} stale-running ({time.time()-started:.0f}s ago) → cancelled')
        # running 但没有 started_at（脏数据）→ 标 cancelled（保守）
        elif st == "running" and not started:
            sr[sid] = {
                **info,
                'status': 'cancelled',
                'error': '脏数据：running 但无 started_at',
                'completed_at': time.time(),
            }
            updated = True
            print(f'  Run {run_id}: {sid} running-but-no-started_at → cancelled')

    if updated:
        cur.execute('UPDATE workflow_runs SET stage_results = ? WHERE id = ?',
                    (json.dumps(sr), run_id))
        fixed_count += 1
        print(f'Run {run_id} updated')

conn.commit()
conn.close()
print(f'\n清理完成，{fixed_count} 个 run 被更新')