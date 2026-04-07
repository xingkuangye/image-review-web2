# -*- coding: utf-8 -*-
# Fix scan_and_add_images to handle invalid paths and prevent library from becoming empty

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: scan_and_add_images - add path validation
old_scan = '''def scan_and_add_images(role_id: int, base_path: str):
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

new_scan = '''def scan_and_add_images(role_id: int, base_path: str):
    """扫描目录添加图片"""
    # 检查路径是否存在
    if not os.path.exists(base_path):
        log_message(f"扫描图片失败: 路径不存在 {base_path}")
        return 0
    
    if not os.path.isdir(base_path):
        log_message(f"扫描图片失败: 路径不是目录 {base_path}")
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
                    # 检查文件是否存在且可读
                    if not os.path.isfile(full_path):
                        continue
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO images (path, role_id, created_at) VALUES (?, ?, ?)",
                            (full_path, role_id, now)
                        )
                        added_count += 1
                    except Exception as e:
                        log_message(f"扫描图片时发生错误: {full_path} - {str(e)}")
    except Exception as e:
        log_message(f"扫描目录时发生错误: {base_path} - {str(e)}")
    finally:
        conn.commit()
        conn.close()
    
    log_message(f"扫描完成: {base_path}, 添加 {added_count} 张图片")
    return added_count'''

if old_scan in content:
    content = content.replace(old_scan, new_scan)
    print('Fixed scan_and_add_images')
else:
    print('scan pattern not found')

# Fix 2: refresh_role_images - ensure we don't delete if scan fails
old_refresh = '''def refresh_role_images(role_id: int):
    """刷新角色图片"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM roles WHERE id = ?", (role_id,))
    role = cursor.fetchone()

    if role:
        # 先获取该角色的所有图片ID
        cursor.execute("SELECT id FROM images WHERE role_id = ?", (role_id,))
        image_ids = [row['id'] for row in cursor.fetchall()]
        
        # 删除这些图片的审核记录
        if image_ids:
            placeholders = ','.join('?' * len(image_ids))
            cursor.execute(f"DELETE FROM reviews WHERE image_id IN ({placeholders})", image_ids)
        
        # 删除旧图片记录
        cursor.execute("DELETE FROM images WHERE role_id = ?", (role_id,))
        
        # 重新扫描
        scan_and_add_images(role_id, role['image_path'])

    conn.commit()
    conn.close()'''

new_refresh = '''def refresh_role_images(role_id: int):
    """刷新角色图片"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM roles WHERE id = ?", (role_id,))
    role = cursor.fetchone()

    if not role:
        conn.close()
        log_message(f"刷新角色失败: 角色 {role_id} 不存在")
        return False
    
    image_path = role['image_path']
    
    # 先获取该角色的所有图片ID（用于删除审核记录）
    cursor.execute("SELECT id FROM images WHERE role_id = ?", (role_id,))
    image_ids = [row['id'] for row in cursor.fetchall()]
    
    # 检查新路径是否存在，如果不存在则不删除旧数据
    if not os.path.exists(image_path):
        conn.close()
        log_message(f"刷新角色失败: 新路径不存在 {image_path}")
        return False
    
    # 删除这些图片的审核记录
    if image_ids:
        placeholders = ','.join('?' * len(image_ids))
        cursor.execute(f"DELETE FROM reviews WHERE image_id IN ({placeholders})", image_ids)
    
    # 删除旧图片记录
    cursor.execute("DELETE FROM images WHERE role_id = ?", (role_id,))
    conn.commit()
    conn.close()
    
    # 重新扫描（在新连接中执行，避免阻塞）
    scan_and_add_images(role_id, image_path)
    
    log_message(f"刷新角色 {role_id} 完成")
    return True'''

if old_refresh in content:
    content = content.replace(old_refresh, new_refresh)
    print('Fixed refresh_role_images')
else:
    print('refresh pattern not found')

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done!')
