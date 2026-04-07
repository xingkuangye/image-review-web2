# -*- coding: utf-8 -*-

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add API endpoint to get required votes config
# Find a good place to add it - after existing settings endpoints

old_settings = '''@app.get("/api/settings/title")
async def get_title():
    """获取页面标题"""
    return {"title": get_setting("title") or "图片审核系统"}'''

new_settings = '''@app.get("/api/settings/title")
async def get_title():
    """获取页面标题"""
    return {"title": get_setting("title") or "图片审核系统"}

@app.get("/api/settings/votes")
async def get_votes_config():
    """获取投票配置"""
    from backend.services import REQUIRED_VOTES
    return {"required_votes": REQUIRED_VOTES}'''

if old_settings in content:
    content = content.replace(old_settings, new_settings)
    print("Fixed: Added /api/settings/votes endpoint")
else:
    print("ERROR: settings pattern not found")

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
