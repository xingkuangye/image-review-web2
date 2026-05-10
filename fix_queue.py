# -*- coding: utf-8 -*-
import os

path = r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\backend\main.py'
with open(path, 'rb') as f:
    content = f.read()

# 查找并替换下载接口
target = b'@app.get("/api/image/{image_id}/download")\r\nasync def download_image(image_id: int, user_id: str = None):'

replacement = b'@app.get("/api/image/{image_id}/download")\r\nasync def download_image(image_id: int):'

if target in content:
    print('Found target, replacing...')
    content = content.replace(target, replacement)
    
    # 找到函数体并替换
    # 查找整个函数的开始和结束
    func_start = content.find(target)
    
    # 找到新函数的定义结束（下一个空行）
    func_def_end = content.find(b'\r\n\r\n\r\n', func_start)
    
    # 新的简单函数体
    new_body = b'''async def download_image(image_id: int):
    """下载原图"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
    image = cursor.fetchone()
    conn.close()

    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    return FileResponse(image['path'])


'''
    
    # 找到旧函数体的结束位置（下一个 @app 或 def）
    next_def = content.find(b'\n\n@app.', func_start + len(target))
    next_def2 = content.find(b'\n\n\ndef _compress_image', func_start + len(target))
    
    if next_def2 > 0 and (next_def == -1 or next_def2 < next_def):
        next_def = next_def2
    
    if next_def > 0:
        content = content[:func_start] + new_body.encode() + content[next_def:]
    
    with open(path, 'wb') as f:
        f.write(content)
    print('Done!')
else:
    print('Target not found')
    # 打印附近内容帮助调试
    idx = content.find(b'download_image')
    if idx > 0:
        print('Context:', repr(content[idx-50:idx+200]))