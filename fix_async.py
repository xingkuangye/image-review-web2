# -*- coding: utf-8 -*-
import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: admin_refresh_role
old_refresh = '''@app.post("/api/admin/roles/{role_id}/refresh")
async def admin_refresh_role(role_id: int, x_admin_password: str = Header(None)):
    """刷新角色图片"""
    verify_admin(x_admin_password)
    refresh_role_images(role_id)
    log_message(f"刷新角色 {role_id} 图片")
    return {"success": True}'''

new_refresh = '''@app.post("/api/admin/roles/{role_id}/refresh")
async def admin_refresh_role(role_id: int, x_admin_password: str = Header(None)):
    """刷新角色图片"""
    verify_admin(x_admin_password)
    # 使用线程池执行器避免阻塞事件循环
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, refresh_role_images, role_id)
    log_message(f"刷新角色 {role_id} 图片")
    return {"success": True}'''

if old_refresh in content:
    content = content.replace(old_refresh, new_refresh)
    print("Fixed: admin_refresh_role")
else:
    print("ERROR: admin_refresh_role pattern not found")

# Fix 2: admin_update_role - refresh_images section
old_update_refresh = '''    # 如果需要刷新图片
    if refresh_images and refresh_images.lower() == 'true':
        refresh_role_images(role_id)'''

new_update_refresh = '''    # 如果需要刷新图片，使用线程池执行器避免阻塞
    if refresh_images and refresh_images.lower() == 'true':
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, refresh_role_images, role_id)'''

if old_update_refresh in content:
    content = content.replace(old_update_refresh, new_update_refresh)
    print("Fixed: admin_update_role refresh section")
else:
    print("ERROR: admin_update_role pattern not found")

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
