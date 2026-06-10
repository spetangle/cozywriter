"""inspect stage_results in DB"""
import json
import sqlite3
conn = sqlite3.connect('data/cozywriter.db')
cur = conn.cursor()
cur.execute('SELECT id, project_id, name, status, stage_results FROM workflow_runs ORDER BY id DESC LIMIT 5')
for row in cur.fetchall():
    print(f'=== Run {row[0]} (project={row[1]}, name={row[2]}, status={row[3]}) ===')
    try:
        sr = json.loads(row[4]) if row[4] else {}
        for sid, info in sr.items():
            if isinstance(info, dict):
                status = info.get('status')
                started = info.get('started_at')
                completed = info.get('completed_at')
                print(f'  {sid}: status={status!r} started_at={started} completed_at={completed}')
                # Check if started_at looks valid
                if started is not None and started < 1000000000:  # before 2001-09
                    print(f'    ⚠️ started_at is too small (< 1e9), looks invalid')
    except Exception as e:
        print(f'  parse error: {e}')
conn.close()