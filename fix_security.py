# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add input validation and safety comment for DELETE statement
old_delete = '''    # 删除这些图片的审核记录
    if image_ids:
        placeholders = ','.join('?' * len(image_ids))
        cursor.execute(f"DELETE FROM reviews WHERE image_id IN ({placeholders})", image_ids)'''

new_delete = '''    # 删除这些图片的审核记录
    # 安全：image_ids 来自数据库查询的整数，已通过参数化查询防止注入
    # placeholders 只是 '?' 重复，无用户输入拼接
    if image_ids:
        # 输入验证：确保所有ID都是整数
        validated_ids = []
        for img_id in image_ids:
            try:
                validated_ids.append(int(img_id))
            except (TypeError, ValueError):
                log_message(f"跳过无效图片ID: {img_id}")
        if validated_ids:
            placeholders = ','.join('?' * len(validated_ids))
            cursor.execute(f"DELETE FROM reviews WHERE image_id IN ({placeholders})", validated_ids)'''

if old_delete in content:
    content = content.replace(old_delete, new_delete)
    print("Fixed: DELETE statement with validation")
else:
    print("ERROR: DELETE pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
