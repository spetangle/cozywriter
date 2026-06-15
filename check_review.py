"""Check current review sessions state."""
import sqlite3
DB = "data/cozywriter.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=" * 70)
print("ReviewSessions (detailed)")
print("=" * 70)
cur.execute("""
    SELECT id, chapter_id, overall_score,
           score_consistency, score_pacing, score_style, score_ai_removal,
           score_word_count, score_foreshadowing, score_character_arc, score_thematic,
           LENGTH(COALESCE(critique, '')) AS critique_len,
           LENGTH(COALESCE(suggestions, '')) AS suggestions_len,
           LENGTH(COALESCE(content_reviewed, '')) AS content_len,
           created_at
    FROM review_sessions
    ORDER BY id
""")
for r in cur.fetchall():
    print(f"  rs#{r[0]} ch={r[1]} created={r[12]}")
    print(f"    overall={r[2]}")
    print(f"    scores: 一致性={r[3]} 节奏={r[4]} 文笔={r[5]} 去AI={r[6]} 字数={r[7]} 伏笔={r[8]} 弧光={r[9]} 主旨={r[10]}")
    print(f"    critique={r[11]}字  content_reviewed={r[12]}字  created_at={r[13]}")
    print()

# Also check chapter_outlines
print("=" * 70)
print("ChapterOutlines (detailed)")
print("=" * 70)
cur.execute("""
    SELECT id, chapter_id, status, LENGTH(COALESCE(key_content, '')) AS key_len,
           LENGTH(COALESCE(plot_advance, '')) AS plot_len,
           chapter_position, pacing, target_word_count,
           LENGTH(COALESCE(notes, '')) AS notes_len,
           LENGTH(COALESCE(CAST(qi_cheng_zhuan_he AS TEXT), '{}')) AS qczh_len,
           LENGTH(COALESCE(CAST(pacing_hooks AS TEXT), '[]')) AS ph_len,
           created_at, updated_at
    FROM chapter_outlines
    ORDER BY id
""")
for r in cur.fetchall():
    print(f"  co#{r[0]} ch={r[1]} status={r[2]} created={r[10]}")
    print(f"    key_content={r[3]}字 plot_advance={r[4]}字")
    print(f"    position='{r[5]}' pacing='{r[6]}' target={r[7]}")
    print(f"    notes={r[8]}字 qi_cheng_zhuan_he={r[9]}字 pacing_hooks={r[10]}字")
    print()

conn.close()
