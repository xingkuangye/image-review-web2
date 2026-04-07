# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Use executemany instead of Python loop
old_delete = '''        if validated_ids:
            # 使用 executemany 批量删除，避免字符串拼接
            for img_id in validated_ids:
                cursor.execute("DELETE FROM reviews WHERE image_id = ?", (img_id,))'''

new_delete = '''        if validated_ids:
            # 使用 executemany 批量删除，避免多次往返数据库，同时使用参数化查询防止注入
            cursor.executemany(
                "DELETE FROM reviews WHERE image_id = ?",
                [(img_id,) for img_id in validated_ids],
            )'''

if old_delete in content:
    content = content.replace(old_delete, new_delete)
    print("Fixed: executemany")
else:
    print("ERROR: executemany pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
