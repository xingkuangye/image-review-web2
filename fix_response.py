# -*- coding: utf-8 -*-

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Return refresh_success in API response
old_return = '''    # 如果需要刷新图片，使用线程池执行器避免阻塞
    refresh_success = True
    if refresh_images and refresh_images.lower() == 'true':
        loop = asyncio.get_running_loop()
        refresh_success = await loop.run_in_executor(None, refresh_role_images, role_id)
        if not refresh_success:
            log_message(f"修改角色 {role_id} 时刷新图片失败")
    
    conn.close()
    log_message(f"修改角色 {role_id}: {name} (路径: {image_path})")
    return {"success": True}'''

new_return = '''    # 如果需要刷新图片，使用线程池执行器避免阻塞
    refresh_success = True
    if refresh_images and refresh_images.lower() == 'true':
        loop = asyncio.get_running_loop()
        refresh_success = await loop.run_in_executor(None, refresh_role_images, role_id)
        if not refresh_success:
            log_message(f"修改角色 {role_id} 时刷新图片失败")
    
    conn.close()
    log_message(f"修改角色 {role_id}: {name} (路径: {image_path})")
    
    # 返回包括刷新状态的结果
    if not refresh_success:
        return {"success": True, "refresh_success": False, "error": "角色信息已更新，但刷新图片失败，可能是路径无效"}
    return {"success": True}'''

if old_return in content:
    content = content.replace(old_return, new_return)
    print("Fixed: refresh_success response")
else:
    print("ERROR: refresh_success pattern not found")

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
