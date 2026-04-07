# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add alias for derived table
old_subquery = '''COALESCE((
                SELECT COUNT(*) FROM (
                    SELECT rev.image_id
                    FROM reviews rev
                    JOIN images img ON rev.image_id = img.id
                    WHERE img.role_id = r.id
                    AND rev.status != 'skip'
                    GROUP BY rev.image_id
                    HAVING COUNT(*) >= ? AND SUM(CASE WHEN rev.status = 'pass' THEN 1 ELSE 0 END) = COUNT(*)
                )
            ), 0) as completed_images'''

new_subquery = '''COALESCE((
                SELECT COUNT(*) FROM (
                    SELECT rev.image_id
                    FROM reviews rev
                    JOIN images img ON rev.image_id = img.id
                    WHERE img.role_id = r.id
                    AND rev.status != 'skip'
                    GROUP BY rev.image_id
                    HAVING COUNT(*) >= ? AND SUM(CASE WHEN rev.status = 'pass' THEN 1 ELSE 0 END) = COUNT(*)
                ) AS completed
            ), 0) as completed_images'''

if old_subquery in content:
    content = content.replace(old_subquery, new_subquery)
    print("Fixed: Added AS completed alias")
else:
    print("ERROR: Subquery pattern not found")

# Fix 2: Replace DELETE with safe approach using executemany
old_delete = '''        if validated_ids:
            placeholders = ','.join('?' * len(validated_ids))
            cursor.execute(f"DELETE FROM reviews WHERE image_id IN ({placeholders})", validated_ids)'''

new_delete = '''        if validated_ids:
            # 使用 executemany 批量删除，避免字符串拼接
            for img_id in validated_ids:
                cursor.execute("DELETE FROM reviews WHERE image_id = ?", (img_id,))'''

if old_delete in content:
    content = content.replace(old_delete, new_delete)
    print("Fixed: Changed DELETE to executemany")
else:
    print("ERROR: DELETE pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
