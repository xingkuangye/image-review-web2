# -*- coding: utf-8 -*-
import re

# Read the file
with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the function
old_func = '''def scan_and_add_images(role_id: int, base_path: str):
    """扫描目录添加图片"""
    conn = get_db()
    cursor = conn.cursor()
    
    supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    now = datetime.now().isoformat()
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in supported_formats:
                full_path = os.path.join(root, file)
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO images (path, role_id, created_at) VALUES (?, ?, ?)",
                        (full_path, role_id, now)
                    )
                except Exception as e:
                    log_message(f"扫描图片时发生错误: {full_path} - {str(e)}")
    
    conn.commit()
    conn.close()'''

new_func = '''def scan_and_add_images(role_id: int, base_path: str):
    """扫描目录添加图片"""
    # 验证路径存在，避免 os.walk 在无效路径上卡死
    if not os.path.exists(base_path):
        log_message(f"扫描图片失败: 路径不存在 {base_path}")
        return 0
    
    conn = get_db()
    cursor = conn.cursor()
    
    supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    now = datetime.now().isoformat()
    
    added_count = 0
    try:
        for root, dirs, files in os.walk(base_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_formats:
                    full_path = os.path.join(root, file)
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO images (path, role_id, created_at) VALUES (?, ?, ?)",
                            (full_path, role_id, now)
                        )
                        if cursor.rowcount > 0:
                            added_count += 1
                    except Exception as e:
                        log_message(f"扫描图片时发生错误: {full_path} - {str(e)}")
    finally:
        conn.commit()
        conn.close()
    
    return added_count'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open('backend/services.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Success: scan_and_add_images fixed!")
else:
    print("ERROR: Pattern not found!")
    # Debug: show what we have
    start = content.find('def scan_and_add_images')
    end = content.find('def get_image_for_review')
    if start != -1 and end != -1:
        actual = content[start:end]
        print(f"Actual function ({len(actual)} chars):")
        print(repr(actual[:300]))
