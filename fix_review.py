# -*- coding: utf-8 -*-
import re

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: get_all_roles - wrap subquery in another SELECT to avoid multiple rows
old_sql = '''COALESCE((
                SELECT COUNT(*)
                FROM reviews rev
                JOIN images img ON rev.image_id = img.id
                WHERE img.role_id = r.id
                AND rev.status != 'skip'
                GROUP BY rev.image_id
                HAVING COUNT(*) >= ? AND SUM(CASE WHEN rev.status = 'pass' THEN 1 ELSE 0 END) = COUNT(*)
            ), 0) as completed_images'''

new_sql = '''COALESCE((
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

if old_sql in content:
    content = content.replace(old_sql, new_sql)
    print("Fixed: completed_images subquery")
else:
    print("ERROR: completed_images pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
