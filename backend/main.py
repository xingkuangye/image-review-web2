import os
import uuid
import secrets
import logging
logger = logging.getLogger(__name__)
import zipfile
import shutil
import asyncio
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
from collections import deque

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from PIL import Image
import io
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db, get_db
from backend.models import *
from backend.services import *

# 安全常量
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
THUMBNAIL_MAX_SIZE = 800  # 缩略图最大边长

# ============ 图片加载排队机制 ============
# 每个用户的最大并发下载数
MAX_CONCURRENT_DOWNLOADS_PER_USER = 2
# 排队超时时间（秒）
QUEUE_TIMEOUT = 60
# 每个用户的当前下载计数
user_active_downloads: Dict[str, int] = {}
# 用户队列锁
queue_lock = asyncio.Lock()

async def wait_for_download_slot(user_id: str) -> bool:
    """等待下载槽位"""
    start_time = time.time()
    while time.time() - start_time < QUEUE_TIMEOUT:
        async with queue_lock:
            active = user_active_downloads.get(user_id, 0)
            if active < MAX_CONCURRENT_DOWNLOADS_PER_USER:
                user_active_downloads[user_id] = active + 1
                return True

        await asyncio.sleep(0.1)

    return False

async def release_download_slot(user_id: str):
    """释放下载槽位 - 递减计数"""
    async with queue_lock:
        if user_id in user_active_downloads and user_active_downloads[user_id] > 0:
            user_active_downloads[user_id] -= 1

# 初始化 - 支持直接运行和模块运行
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(title="图片审核系统")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ============ 定时备份调度器 ============
scheduler_running = True

def run_auto_backup():
    """执行自动备份"""
    try:
        from backend.backup import create_backup, cleanup_old_backups
        from backend.services import get_backup_retention_days

        log_message("定时备份开始...")
        backup_path = create_backup()

        if backup_path:
            cleanup_old_backups(get_backup_retention_days())
            log_message(f"定时备份成功: {backup_path}")
        else:
            log_message("定时备份失败")
    except Exception as e:
        log_message(f"定时备份异常: {str(e)}")

def backup_scheduler():
    """备份调度器线程"""
    global scheduler_running
    # 从数据库读取上次备份日期（持久化）
    last_backup_date = get_last_backup_date()

    while scheduler_running:
        try:
            if not get_auto_backup_enabled():
                time.sleep(60)  # 每分钟检查一次
                continue

            now = datetime.now()
            current_time = now.strftime("%H:%M")
            target_time = get_auto_backup_time()
            today_str = now.strftime("%Y-%m-%d")

            # 检查是否到达备份时间且今天尚未备份
            if current_time == target_time and last_backup_date != today_str:
                run_auto_backup()
                last_backup_date = today_str
                set_last_backup_date(today_str)  # 持久化到数据库
                log_message(f"自动备份已执行，下次于 {target_time} 执行")

        except Exception as e:
            log_message(f"调度器异常: {str(e)}")

        time.sleep(30)  # 每30秒检查一次

@app.on_event("startup")
async def startup():
    global admin_password, scheduler_running
    init_db()
    admin_password = get_admin_password()
    # 安全：不打印密码到日志和终端
    print(f"\n{'='*50}")
    print(f"图片审核系统已启动")
    print(f"请使用管理员密码登录")
    print(f"{'='*50}\n")

    # 启动时检查：如果已过备份时间且今天未备份，立即备份
    if get_auto_backup_enabled():
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        target_time = get_auto_backup_time()
        today_str = now.strftime("%Y-%m-%d")
        last_backup = get_last_backup_date()

        if current_time > target_time and last_backup != today_str:
            log_message(f"启动时检测到今日未备份，立即执行...")
            run_auto_backup()
            set_last_backup_date(today_str)

    # 启动备份调度器
    scheduler_running = True
    scheduler_thread = threading.Thread(target=backup_scheduler, daemon=True)
    scheduler_thread.start()

@app.on_event("shutdown")
async def shutdown():
    global scheduler_running
    scheduler_running = False
    log_message("自动备份调度器已停止")

# ============ 管理员认证 ============

admin_password = None

def get_or_generate_admin_password():
    """获取或生成管理员密码（仅在首次访问时生成）"""
    global admin_password
    if admin_password is None:
        admin_password = generate_admin_password()
    return admin_password

def verify_admin(x_admin_password: str = Header(None)):
    global admin_password
    if admin_password is None:
        admin_password = generate_admin_password()
    if x_admin_password != admin_password:
        raise HTTPException(status_code=401, detail="密码错误")

# ============ 前台API ============

@app.get("/api/user/init")
async def init_user():
    """初始化用户，返回用户ID"""
    user_id = str(uuid.uuid4())
    user = create_or_get_user(user_id)
    log_message(f"新用户创建: {user_id}")
    return user

@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    """获取用户信息"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user['is_banned']:
        raise HTTPException(status_code=403, detail="用户已被封禁")

    update_user_activity(user_id)
    return create_or_get_user(user_id)

@app.put("/api/user/{user_id}/nickname")
async def update_nickname(user_id: str, data: UserUpdate):
    """更新昵称"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user['is_banned']:
        raise HTTPException(status_code=403, detail="用户已被封禁")

    update_user_nickname(user_id, data.nickname)
    return {"success": True}

@app.get("/api/image/review")
async def get_review_image(
    user_id: str,
    role_id: Optional[int] = None
):
    """获取待审核图片"""
    # 检查用户状态
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user['is_banned']:
        raise HTTPException(status_code=403, detail="用户已被封禁")

    update_user_activity(user_id)
    image = get_image_for_review(user_id, role_id)

    if not image:
        return JSONResponse(content={"message": "暂无待审核图片", "image": None})

    return {"image": image}

@app.post("/api/image/{image_id}/review")
async def submit_image_review(
    image_id: int,
    user_id: str = Form(...),
    status: str = Form(...)
):
    """提交审核结果"""
    if status not in ['pass', 'fail', 'skip']:
        raise HTTPException(status_code=400, detail="无效的审核状态")

    submit_review(image_id, user_id, status)
    log_message(f"用户 {user_id} 审核图片 {image_id}: {status}")
    return {"success": True}

@app.get("/api/image/{image_id}/download")
async def download_image(image_id: int, user_id: str = None):
    """下载原图 - 支持并发控制"""
    if user_id:
        got_slot = await wait_for_download_slot(user_id)
        if not got_slot:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
            image = cursor.fetchone()
            conn.close()
            if not image:
                raise HTTPException(status_code=404, detail="图片不存在")
            return FileResponse(image['path'])
        finally:
            await release_download_slot(user_id)
    else:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
        image = cursor.fetchone()
        conn.close()
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        return FileResponse(image['path'])\n\ndef _compress_image(img, max_size=500*1024, initial_quality=85, quality_step=10,

                       min_quality=20, min_width=200, max_iterations=15):

    """ÃÂ¥ÃÂÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂ°ÃÂ¦ÃÂÃÂÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¥ÃÂ°ÃÂÃÂ©ÃÂÃÂÃÂ¥ÃÂÃÂ¶ÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

    

    Args:

        img: PIL ImageÃÂ¥ÃÂ¯ÃÂ¹ÃÂ¨ÃÂ±ÃÂ¡ÃÂ¯ÃÂ¼ÃÂÃÂ¤ÃÂ¸ÃÂÃÂ¤ÃÂ¼ÃÂÃÂ¤ÃÂ¿ÃÂ®ÃÂ¦ÃÂÃÂ¹ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ¾ÃÂ¯ÃÂ¼ÃÂ

        max_size: ÃÂ¦ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ¤ÃÂ§ÃÂ¥ÃÂ°ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¨ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¤500KB

        initial_quality: ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ§ÃÂÃÂ¥ÃÂÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¨ÃÂ´ÃÂ¨ÃÂ©ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¯ÃÂ¿ÃÂ½?5

        quality_step: ÃÂ¨ÃÂ´ÃÂ¨ÃÂ©ÃÂÃÂÃÂ©ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂ­ÃÂ¥ÃÂ©ÃÂÃÂ¿ÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¯ÃÂ¿ÃÂ½?0

        min_quality: ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ½ÃÂÃÂ¨ÃÂ´ÃÂ¨ÃÂ©ÃÂÃÂÃÂ©ÃÂÃÂÃÂ¥ÃÂÃÂ¼ÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¤20

        min_width: ÃÂ¦ÃÂÃÂÃÂ¥ÃÂ°ÃÂÃÂ¥ÃÂ®ÃÂ½ÃÂ¥ÃÂºÃÂ¦ÃÂ©ÃÂÃÂÃÂ¥ÃÂÃÂ¼ÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¤200px

        max_iterations: ÃÂ¦ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¨ÃÂ¿ÃÂ­ÃÂ¤ÃÂ»ÃÂ£ÃÂ¦ÃÂ¬ÃÂ¡ÃÂ¦ÃÂÃÂ°ÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¤15

    

    Returns:

        bytes: ÃÂ¥ÃÂÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂJPEGÃÂ¥ÃÂ­ÃÂÃÂ¨ÃÂÃÂÃÂ¦ÃÂÃÂ°ÃÂ¦ÃÂÃÂ®

    """

    # ÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂÃÂ¯ÃÂ¦ÃÂÃÂ¬ÃÂ¤ÃÂ¸ÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ½ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂÃÂ¿ÃÂ¥ÃÂÃÂÃÂ¤ÃÂ¿ÃÂ®ÃÂ¦ÃÂÃÂ¹ÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

    img = img.copy()

    quality = initial_quality

    iterations = 0

    best_bytes = None

    best_size = float('inf')

    

    while iterations < max_iterations:

        iterations += 1

        output = io.BytesIO()

        img.save(output, format='JPEG', quality=quality, optimize=True)

        output.seek(0)

        data = output.getvalue()

        size = len(data)

        

        if size <= max_size:

            return data

        

        # ÃÂ¨ÃÂ®ÃÂ°ÃÂ¥ÃÂ½ÃÂÃÂ¥ÃÂ½ÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ½ÃÂ³ÃÂ§ÃÂ»ÃÂÃÂ¯ÃÂ¿ÃÂ½?

        if size < best_size:

            best_bytes = data

            best_size = size

        

        # ÃÂ¨ÃÂ¾ÃÂ¾ÃÂ¥ÃÂÃÂ°ÃÂ¨ÃÂ´ÃÂ¨ÃÂ©ÃÂÃÂÃÂ¤ÃÂ¸ÃÂÃÂ©ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂ°ÃÂÃÂ¨ÃÂ¯ÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¥ÃÂ°ÃÂÃÂ¥ÃÂ°ÃÂºÃÂ¥ÃÂ¯ÃÂ¸

        if quality <= min_quality and img.size[0] > min_width:

            new_size = (int(img.size[0] * 0.75), int(img.size[1] * 0.75))

            img = img.resize(new_size, Image.Resampling.LANCZOS)

            quality = min(quality + quality_step, 70) if iterations > 3 else quality

            continue

        

        # ÃÂ©ÃÂÃÂÃÂ¤ÃÂ½ÃÂÃÂ¨ÃÂ´ÃÂ¨ÃÂ©ÃÂÃÂ

        if quality > min_quality:

            quality -= quality_step

        elif img.size[0] > min_width:

            new_size = (int(img.size[0] * 0.75), int(img.size[1] * 0.75))

            img = img.resize(new_size, Image.Resampling.LANCZOS)

        else:

            break

    

    # ÃÂ¥ÃÂ¦ÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ¿ÃÂ­ÃÂ¤ÃÂ»ÃÂ£ÃÂ©ÃÂÃÂ½ÃÂ¦ÃÂÃÂ ÃÂ¦ÃÂ³ÃÂÃÂ¦ÃÂ»ÃÂ¡ÃÂ¨ÃÂ¶ÃÂ³ÃÂ¥ÃÂ¤ÃÂ§ÃÂ¥ÃÂ°ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ¦ÃÂ±ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ½ÃÂ³ÃÂ§ÃÂ»ÃÂÃÂ¯ÃÂ¿ÃÂ½?

    if best_bytes is not None:

        return best_bytes

    

    # ÃÂ¦ÃÂÃÂÃÂ§ÃÂ»ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂºÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂ¼ÃÂºÃÂ¥ÃÂÃÂ¶ÃÂ¤ÃÂ½ÃÂ¿ÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ½ÃÂÃÂ¨ÃÂ´ÃÂ¨ÃÂ¯ÃÂ¿ÃÂ½?

    output = io.BytesIO()

    img.save(output, format='JPEG', quality=min_quality, optimize=True)

    return output.getvalue()





@app.get("/api/image/{image_id}/thumbnail")

async def get_thumbnail(image_id: int):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ§ÃÂ¼ÃÂ©ÃÂ§ÃÂÃÂ¥ÃÂ¥ÃÂÃÂ¾ÃÂ¯ÃÂ¼ÃÂÃÂ§ÃÂ¡ÃÂ®ÃÂ¤ÃÂ¿ÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ°ÃÂÃÂ¤ÃÂºÃÂ500KB"""

    conn = get_db()

    cursor = conn.cursor()

    cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))

    image = cursor.fetchone()

    conn.close()



    if not image:

        raise HTTPException(status_code=404, detail="ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¯ÃÂ¿ÃÂ½?)



    original_path = image['path']



    try:

        with Image.open(original_path) as img:

            # ÃÂ¨ÃÂ½ÃÂ¬ÃÂ¦ÃÂÃÂ¢ÃÂ¯ÃÂ¿ÃÂ½?RGBÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¯ÃÂ¿ÃÂ½?PNG ÃÂ©ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ©ÃÂÃÂÃÂ©ÃÂÃÂÃÂ§ÃÂ­ÃÂÃÂ¯ÃÂ¼ÃÂ

            if img.mode in ('RGBA', 'LA', 'P'):

                img = img.convert('RGB')



            # ÃÂ¨ÃÂ®ÃÂ¡ÃÂ§ÃÂ®ÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¦ÃÂÃÂ¾ÃÂ¦ÃÂ¯ÃÂÃÂ¤ÃÂ¾ÃÂ

            width, height = img.size

            if width > THUMBNAIL_MAX_SIZE or height > THUMBNAIL_MAX_SIZE:

                ratio = min(THUMBNAIL_MAX_SIZE / width, THUMBNAIL_MAX_SIZE / height)

                new_width = int(width * ratio)

                new_height = int(height * ratio)

                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)



            # ÃÂ¥ÃÂÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ¯ÃÂ¿ÃÂ½?00KBÃÂ¤ÃÂ»ÃÂ¥ÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ§ÃÂÃÂ´ÃÂ¦ÃÂÃÂ¥ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂ­ÃÂÃÂ¨ÃÂÃÂÃÂ¦ÃÂÃÂ°ÃÂ¯ÃÂ¿ÃÂ½?

            compressed_data = _compress_image(img)

            return StreamingResponse(

                io.BytesIO(compressed_data),

                media_type="image/jpeg"

            )



    except Exception:

        # ÃÂ¨ÃÂ®ÃÂ°ÃÂ¥ÃÂ½ÃÂÃÂ§ÃÂ¼ÃÂ©ÃÂ§ÃÂÃÂ¥ÃÂ¥ÃÂÃÂ¾ÃÂ¥ÃÂ¤ÃÂÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥ÃÂ§ÃÂÃÂÃÂ¥ÃÂ¼ÃÂÃÂ¥ÃÂ¸ÃÂ¸ÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂÃÂ¿ÃÂ¥ÃÂÃÂÃÂ©ÃÂÃÂÃÂ©ÃÂ»ÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¯ÃÂ¿ÃÂ½?

        logger.exception("ÃÂ§ÃÂ¼ÃÂ©ÃÂ§ÃÂÃÂ¥ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¯ÃÂ¿ÃÂ½?%s, ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ¾", original_path)

        return FileResponse(original_path)



@app.get("/api/stats")

async def get_stats():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ§ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¡ÃÂ¦ÃÂÃÂ°ÃÂ¦ÃÂÃÂ®"""

    return get_overall_stats()



@app.get("/api/roles")

async def get_roles():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    return get_all_roles()



@app.get("/api/admin/disputed-images")

async def admin_get_disputed_images(x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂºÃÂÃÂ¨ÃÂ®ÃÂ®ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂÃÂÃÂ¨ÃÂ¦ÃÂÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ©ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    return get_disputed_images()



@app.get("/api/settings")

async def get_all_settings():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ®ÃÂ¾ÃÂ¯ÃÂ¿ÃÂ½?""

    return get_settings()



@app.get("/api/settings/review-rule")

async def get_review_rule_api():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ§ÃÂÃÂ¥ÃÂÃÂ"""

    return {"content": get_setting("review_rule") or ""}



@app.get("/api/settings/title")

async def get_title():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ©ÃÂ¡ÃÂµÃÂ©ÃÂÃÂ¢ÃÂ¦ÃÂ ÃÂÃÂ©ÃÂ¢ÃÂ"""

    return {"title": get_setting("title") or "ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ§ÃÂ³ÃÂ»ÃÂ§ÃÂ»ÃÂ"}



@app.get("/api/settings/votes")

async def get_votes_config():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ§ÃÂ¥ÃÂ¨ÃÂ©ÃÂÃÂÃÂ§ÃÂ½ÃÂ®"""

    from backend.services import REQUIRED_VOTES

    return {"required_votes": REQUIRED_VOTES}



@app.get("/api/settings/icon")

async def get_icon():

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ©ÃÂ¡ÃÂµÃÂ©ÃÂÃÂ¢ÃÂ¥ÃÂÃÂ¾ÃÂ¦ÃÂ ÃÂ"""

    return {"icon": get_setting("icon") or ""}



# ============ ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ°API ============



@app.get("/api/admin/verify")

async def verify_admin_password(x_admin_password: str = Header(None)):

    """ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂ¯ÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    global admin_password

    if admin_password is None:

        admin_password = generate_admin_password()

    

    if x_admin_password != admin_password:

        return {"valid": False}

    return {"valid": True}



@app.post("/api/admin/roles")

async def admin_create_role(

    name: str = Form(...),

    image_path: str = Form(...),

    avatar: UploadFile = File(None),

    x_admin_password: str = Header(None)

):

    """ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ»ÃÂºÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²"""

    verify_admin(x_admin_password)

    

    avatar_path = None

    if avatar:

        # ÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ¯ÃÂ¼ÃÂÃÂ¦ÃÂ£ÃÂÃÂ¦ÃÂÃÂ¥ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ¤ÃÂ§ÃÂ¯ÃÂ¿ÃÂ½?

        avatar_content = await avatar.read()

        if len(avatar_content) > MAX_FILE_SIZE:

            raise HTTPException(status_code=400, detail="ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¯ÃÂ¼ÃÂÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?MB")

        

        # ÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂªÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ©ÃÂÃÂ²ÃÂ¦ÃÂ­ÃÂ¢ÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂÃÂ©ÃÂÃÂÃÂ¥ÃÂÃÂ

        safe_filename = os.path.basename(avatar.filename)

        filename = f"{uuid.uuid4()}_{safe_filename}"

        avatar_path = os.path.join(UPLOADS_DIR, filename)

        with open(avatar_path, 'wb') as f:

            f.write(avatar_content)

    

    role = create_role(name, image_path, avatar_path)

    log_message(f"ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ»ÃÂºÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²: {name} (ÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂ: {image_path})")

    return role



@app.get("/api/admin/roles")

async def admin_get_roles(x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    return get_all_roles()



@app.post("/api/admin/roles/{role_id}/refresh")

async def admin_refresh_role(role_id: int, x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂ"""

    verify_admin(x_admin_password)

    # ÃÂ¤ÃÂ½ÃÂ¿ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂºÃÂ¿ÃÂ§ÃÂ¨ÃÂÃÂ¦ÃÂ±ÃÂ ÃÂ¦ÃÂÃÂ§ÃÂ¨ÃÂ¡ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ©ÃÂÃÂ¿ÃÂ¥ÃÂÃÂÃÂ©ÃÂÃÂ»ÃÂ¥ÃÂ¡ÃÂÃÂ¤ÃÂºÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ¾ÃÂªÃÂ§ÃÂÃÂ¯

    loop = asyncio.get_running_loop()

    success = await loop.run_in_executor(None, refresh_role_images, role_id)

    if success:

        log_message(f"ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ² {role_id} ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂ")

        return {"success": True}

    else:

        log_message(f"ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ² {role_id} ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥")

        return {"success": False, "error": "ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥ÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂ¯ÃÂ¨ÃÂÃÂ½ÃÂ¦ÃÂÃÂ¯ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ¦ÃÂÃÂÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂÃÂ¦ÃÂÃÂ ÃÂ¦ÃÂÃÂ"}



@app.put("/api/admin/roles/{role_id}")

async def admin_update_role(

    role_id: int,

    name: str = Form(...),

    image_path: str = Form(...),

    refresh_images: str = Form(None),

    avatar: UploadFile = File(None),

    x_admin_password: str = Header(None)

):

    """ÃÂ¤ÃÂ¿ÃÂ®ÃÂ¦ÃÂÃÂ¹ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²"""

    verify_admin(x_admin_password)

    

    conn = get_db()

    cursor = conn.cursor()

    

    # ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ½ÃÂÃÂ¥ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¤ÃÂ¿ÃÂ¡ÃÂ¦ÃÂÃÂ¯

    cursor.execute("SELECT * FROM roles WHERE id = ?", (role_id,))

    role = cursor.fetchone()

    

    if not role:

        conn.close()

        raise HTTPException(status_code=404, detail="ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¯ÃÂ¿ÃÂ½?)

    

    avatar_path = role['avatar_path']

    

    # ÃÂ¥ÃÂ¤ÃÂÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ¤ÃÂ´ÃÂ¯ÃÂ¿ÃÂ½?- ÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂ¤ÃÂÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¥ÃÂ°ÃÂ

    if avatar and avatar.filename:

        avatar_content = await avatar.read()

        if len(avatar_content) > MAX_FILE_SIZE:

            raise HTTPException(status_code=400, detail="ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂ¤ÃÂ§ÃÂ¯ÃÂ¼ÃÂÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?MB")

        

        safe_filename = os.path.basename(avatar.filename)

        filename = f"{uuid.uuid4()}_{safe_filename}"

        avatar_path = os.path.join(UPLOADS_DIR, filename)

        with open(avatar_path, 'wb') as f:

            f.write(avatar_content)

    

    # ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¤ÃÂ¿ÃÂ¡ÃÂ¦ÃÂÃÂ¯

    cursor.execute(

        "UPDATE roles SET name = ?, image_path = ?, avatar_path = ? WHERE id = ?",

        (name, image_path, avatar_path, role_id)

    )

    conn.commit()

    

    # ÃÂ¥ÃÂ¦ÃÂÃÂ¦ÃÂÃÂÃÂ©ÃÂÃÂÃÂ¨ÃÂ¦ÃÂÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¤ÃÂ½ÃÂ¿ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂºÃÂ¿ÃÂ§ÃÂ¨ÃÂÃÂ¦ÃÂ±ÃÂ ÃÂ¦ÃÂÃÂ§ÃÂ¨ÃÂ¡ÃÂÃÂ¥ÃÂÃÂ¨ÃÂ©ÃÂÃÂ¿ÃÂ¥ÃÂÃÂÃÂ©ÃÂÃÂ»ÃÂ¥ÃÂ¡ÃÂ

    refresh_success = True

    if refresh_images and refresh_images.lower() == 'true':

        loop = asyncio.get_running_loop()

        refresh_success = await loop.run_in_executor(None, refresh_role_images, role_id)

        if not refresh_success:

            log_message(f"ÃÂ¤ÃÂ¿ÃÂ®ÃÂ¦ÃÂÃÂ¹ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ² {role_id} ÃÂ¦ÃÂÃÂ¶ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¯ÃÂ¿ÃÂ½?)

    

    conn.close()

    log_message(f"ÃÂ¤ÃÂ¿ÃÂ®ÃÂ¦ÃÂÃÂ¹ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ² {role_id}: {name} (ÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂ: {image_path})")

    

    # ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂ¬ÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ§ÃÂÃÂ¶ÃÂ¦ÃÂÃÂÃÂ§ÃÂÃÂÃÂ§ÃÂ»ÃÂÃÂ¦ÃÂÃÂ

    if not refresh_success:

        return {"success": True, "refresh_success": False, "error": "ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¤ÃÂ¿ÃÂ¡ÃÂ¦ÃÂÃÂ¯ÃÂ¥ÃÂ·ÃÂ²ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¯ÃÂ¼ÃÂÃÂ¤ÃÂ½ÃÂÃÂ¥ÃÂÃÂ·ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥ÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂ¯ÃÂ¨ÃÂÃÂ½ÃÂ¦ÃÂÃÂ¯ÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂÃÂ¦ÃÂÃÂ ÃÂ¯ÃÂ¿ÃÂ½?}

    return {"success": True}



@app.delete("/api/admin/roles/{role_id}")

async def admin_delete_role(role_id: int, x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂÃÂ ÃÂ©ÃÂÃÂ¤ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²"""

    verify_admin(x_admin_password)

    delete_role(role_id)

    log_message(f"ÃÂ¥ÃÂÃÂ ÃÂ©ÃÂÃÂ¤ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ² {role_id}")

    return {"success": True}



@app.get("/api/admin/users")

async def admin_get_users(sort_by: str = "id", x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ§ÃÂÃÂ¨ÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    return get_all_users(sort_by)



@app.get("/api/admin/users/{user_id}/reviews")

async def admin_get_user_reviews(user_id: str, x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ·ÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ®ÃÂ°ÃÂ¥ÃÂ½ÃÂ"""

    verify_admin(x_admin_password)

    return get_user_reviews(user_id)



@app.delete("/api/admin/reviews/{review_id}")

async def admin_delete_review(review_id: int, x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂÃÂ ÃÂ©ÃÂÃÂ¤ÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ®ÃÂ°ÃÂ¥ÃÂ½ÃÂ"""

    verify_admin(x_admin_password)

    delete_review(review_id)

    return {"success": True}



@app.delete("/api/admin/users/{user_id}/reviews")

async def admin_clear_user_reviews(user_id: str, x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂ¸ÃÂÃÂ©ÃÂÃÂ¤ÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ·ÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ®ÃÂ°ÃÂ¥ÃÂ½ÃÂ"""

    verify_admin(x_admin_password)

    clear_user_reviews(user_id)

    log_message(f"ÃÂ¦ÃÂ¸ÃÂÃÂ©ÃÂÃÂ¤ÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ· {user_id} ÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ®ÃÂ°ÃÂ¯ÃÂ¿ÃÂ½?)

    return {"success": True}



@app.post("/api/admin/users/{user_id}/ban")

async def admin_ban_user(user_id: str, banned: bool = Form(True), x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂ°ÃÂÃÂ§ÃÂ¦ÃÂ/ÃÂ¨ÃÂ§ÃÂ£ÃÂ¥ÃÂ°ÃÂÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ·"""

    verify_admin(x_admin_password)

    ban_user(user_id, banned)

    log_message(f"ÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂ· {user_id} {'ÃÂ¥ÃÂ°ÃÂÃÂ§ÃÂ¦ÃÂ' if banned else 'ÃÂ¨ÃÂ§ÃÂ£ÃÂ¥ÃÂ°ÃÂ'}")

    return {"success": True}



@app.get("/api/admin/stats")

async def admin_get_stats(x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ°ÃÂ§ÃÂ»ÃÂÃÂ¨ÃÂ®ÃÂ¡"""

    verify_admin(x_admin_password)

    stats = get_overall_stats()

    roles = get_all_roles()

    

    role_stats = []

    for role in roles:

        rs = get_role_stats(role.id)

        if rs:

            role_stats.append({

                "role": role,

                "stats": rs

            })

    

    return {

        "overall": stats,

        "roles": role_stats

    }



@app.get("/api/admin/export")

async def admin_export_approved(x_admin_password: str = Header(None)):

    """Export all approved images (by role folder).

    Optimization: batch status query, pre-group by role_id, thread pool for DB ops.

    """

    verify_admin(x_admin_password)

    conn = get_db()

    cursor = conn.cursor()



    export_dir = os.path.join(BASE_DIR, 'exports')

    os.makedirs(export_dir, exist_ok=True)



    zip_filename = f"Approved_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    zip_path = os.path.join(export_dir, zip_filename)



    try:

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:

            # Get all roles

            cursor.execute("SELECT id, name FROM roles")

            roles = cursor.fetchall()



            # Batch fetch all images

            cursor.execute("SELECT id, path, role_id FROM images")

            all_images = cursor.fetchall()



            # Pre-group images by role_id (O(I) instead of O(R*I))

            images_by_role = {}

            for img in all_images:

                rid = img['role_id']

                if rid not in images_by_role:

                    images_by_role[rid] = []

                images_by_role[rid].append(img)



            # Batch fetch all image statuses (single query, no N+1)

            image_ids = [img['id'] for img in all_images]

            loop = asyncio.get_running_loop()

            image_statuses = await loop.run_in_executor(

                None, get_image_final_statuses_batch, image_ids

            )



            total_count = 0

            for role in roles:

                role_id, role_name = role['id'], role['name']

                safe_folder_name = "".join(c for c in role_name if c.isalnum() or c in (' ', '-', '_')).strip()

                if not safe_folder_name:

                    safe_folder_name = f"Role{role_id}"



                role_images = images_by_role.get(role_id, [])

                role_pass_count = 0



                for img in role_images:

                    final_status = image_statuses.get(img['id'])

                    if final_status == 'pass':

                        img_path = img['path']

                        if os.path.exists(img_path):

                            arcname = os.path.join(safe_folder_name, os.path.basename(img_path))

                            zipf.write(img_path, arcname)

                            role_pass_count += 1

                            total_count += 1



                log_message(f"Role {role_name}: {role_pass_count} approved")



        log_message(f"Export complete: {total_count} images")



        if total_count == 0:

            if os.path.exists(zip_path):

                os.remove(zip_path)

            return JSONResponse(content={"message": "No approved images", "count": 0})



        return FileResponse(zip_path, filename=zip_filename, media_type='application/zip')



    except Exception as e:

        log_message(f"Export failed: {str(e)}")

        raise HTTPException(status_code=500, detail=str(e))

    finally:

        conn.close()





@app.get("/api/admin/export-disputed")

async def admin_export_disputed(x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂ¯ÃÂ¼ÃÂ¥ÃÂÃÂºÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂºÃÂÃÂ¨ÃÂ®ÃÂ®ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ¤ÃÂ¹ÃÂ¯ÃÂ¼ÃÂ"""

    verify_admin(x_admin_password)

    

    # ÃÂ¤ÃÂ½ÃÂ¿ÃÂ§ÃÂÃÂ¨ÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂ¡ÃÂ¥ÃÂÃÂ½ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¤ÃÂºÃÂÃÂ¨ÃÂ®ÃÂ®ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂ

    disputed_images = get_disputed_images()

    

    if not disputed_images:

        return JSONResponse(content={"message": "ÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂ ÃÂ¥ÃÂÃÂ¯ÃÂ¥ÃÂ¯ÃÂ¼ÃÂ¥ÃÂÃÂºÃÂ¥ÃÂÃÂ¾ÃÂ¯ÃÂ¿ÃÂ½?, "count": 0})

    

    # ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ»ÃÂºÃÂ¥ÃÂ¯ÃÂ¼ÃÂ¥ÃÂÃÂºÃÂ§ÃÂÃÂ®ÃÂ¥ÃÂ½ÃÂ

    export_dir = os.path.join(BASE_DIR, 'exports')

    os.makedirs(export_dir, exist_ok=True)

    

    zip_filename = f"ÃÂ¤ÃÂºÃÂÃÂ¨ÃÂ®ÃÂ®ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    zip_path = os.path.join(export_dir, zip_filename)

    

    try:

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:

            total_count = 0

            

            # ÃÂ¦ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

            role_images = {}

            for img in disputed_images:

                role_name = img.get('role_name') or f"ÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²{img.get('role_id')}"

                if role_name not in role_images:

                    role_images[role_name] = []

                role_images[role_name].append(img)

            

            for role_name, images in role_images.items():

                # ÃÂ¦ÃÂ¸ÃÂÃÂ§ÃÂÃÂÃÂ¨ÃÂ§ÃÂÃÂ¨ÃÂÃÂ²ÃÂ¥ÃÂÃÂÃÂ§ÃÂ§ÃÂ°ÃÂ§ÃÂÃÂ¨ÃÂ¤ÃÂºÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂ¤ÃÂ¹ÃÂ¥ÃÂÃÂ

                safe_folder_name = "".join(c for c in role_name if c.isalnum() or c in (' ', '-', '_')).strip()

                if not safe_folder_name:

                    safe_folder_name = "ÃÂ¦ÃÂÃÂªÃÂ¥ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

                

                for img in images:

                    img_path = img['path']

                    if os.path.exists(img_path):

                        arcname = os.path.join(safe_folder_name, os.path.basename(img_path))

                        zipf.write(img_path, arcname)

                        total_count += 1

            

            log_message(f"ÃÂ¤ÃÂºÃÂÃÂ¨ÃÂ®ÃÂ®ÃÂ¥ÃÂÃÂ¾ÃÂ§ÃÂÃÂÃÂ¥ÃÂ¯ÃÂ¼ÃÂ¥ÃÂÃÂºÃÂ¥ÃÂ®ÃÂÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂ± {total_count} ÃÂ¥ÃÂ¼ÃÂ ÃÂ¥ÃÂÃÂ¾ÃÂ¯ÃÂ¿ÃÂ½?)

        

        return FileResponse(zip_path, filename=zip_filename, media_type='application/zip')

        

    except Exception as e:

        log_message(f"ÃÂ¥ÃÂ¯ÃÂ¼ÃÂ¥ÃÂÃÂºÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥: {str(e)}")

        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/admin/settings")

async def admin_get_settings(x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂÃÂ·ÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¨ÃÂ®ÃÂ¾ÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    return get_settings_all()



@app.put("/api/admin/settings/title")

async def admin_update_title(title: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ©ÃÂ¡ÃÂµÃÂ©ÃÂÃÂ¢ÃÂ¦ÃÂ ÃÂÃÂ©ÃÂ¢ÃÂ"""

    verify_admin(x_admin_password)

    save_setting("title", title)

    return {"success": True}



@app.put("/api/admin/settings/icon")

async def admin_update_icon(icon: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ©ÃÂ¡ÃÂµÃÂ©ÃÂÃÂ¢ÃÂ¥ÃÂÃÂ¾ÃÂ¦ÃÂ ÃÂ"""

    verify_admin(x_admin_password)

    save_setting("icon", icon)

    return {"success": True}



@app.put("/api/admin/settings/review-rule")

async def admin_update_review_rule(content: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ®ÃÂ¡ÃÂ¦ÃÂ ÃÂ¸ÃÂ¨ÃÂ§ÃÂÃÂ¥ÃÂÃÂ"""

    verify_admin(x_admin_password)

    save_setting("review_rule", content)

    return {"success": True}



@app.put("/api/admin/settings/auto-backup-time")

async def admin_update_auto_backup_time(backup_time: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂÃÂªÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¦ÃÂÃÂ¶ÃÂ©ÃÂÃÂ´"""

    verify_admin(x_admin_password)

    save_setting("auto_backup_time", backup_time)

    log_message(f"ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂÃÂªÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¦ÃÂÃÂ¶ÃÂ©ÃÂÃÂ´: {backup_time}")

    return {"success": True}



@app.put("/api/admin/settings/auto-backup-enabled")

async def admin_update_auto_backup_enabled(enabled: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂÃÂªÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¥ÃÂÃÂ¯ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂÃÂ¶ÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    save_setting("auto_backup_enabled", enabled.lower())

    log_message(f"ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¨ÃÂÃÂªÃÂ¥ÃÂÃÂ¨ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¥ÃÂÃÂ¯ÃÂ§ÃÂÃÂ¨ÃÂ§ÃÂÃÂ¶ÃÂ¯ÃÂ¿ÃÂ½? {enabled}")

    return {"success": True}



@app.put("/api/admin/settings/backup-retention-days")

async def admin_update_backup_retention_days(days: str = Form(...), x_admin_password: str = Header(None)):

    """ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¤ÃÂ¿ÃÂÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ©ÃÂ¦ÃÂÃÂ°"""

    verify_admin(x_admin_password)

    save_setting("backup_retention_days", days)

    log_message(f"ÃÂ¦ÃÂÃÂ´ÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¤ÃÂ¿ÃÂÃÂ§ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ©ÃÂ¦ÃÂÃÂ°: {days}ÃÂ¯ÃÂ¿ÃÂ½?)

    return {"success": True}



@app.post("/api/admin/backup/now")

async def admin_backup_now(x_admin_password: str = Header(None)):

    """ÃÂ§ÃÂ«ÃÂÃÂ¥ÃÂÃÂ³ÃÂ¦ÃÂÃÂ§ÃÂ¨ÃÂ¡ÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½"""

    verify_admin(x_admin_password)

    from backend.backup import create_backup, cleanup_old_backups

    backup_path = create_backup()

    if backup_path:

        cleanup_old_backups(get_backup_retention_days())

        log_message(f"ÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂ¨ÃÂ¨ÃÂ§ÃÂ¦ÃÂ¥ÃÂÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?)

        return {"success": True, "message": "ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂ", "path": backup_path}

    return {"success": False, "message": "ÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½ÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥"}



@app.get("/api/admin/backup/list")

async def admin_list_backups(x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂºÃÂ¦ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    verify_admin(x_admin_password)

    from backend.backup import list_backups

    return {"backups": list_backups()}



@app.post("/api/admin/backup/restore/{filename}")

async def admin_restore_backup(filename: str, x_admin_password: str = Header(None)):

    """ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½"""

    import re

    from backend.backup import restore_backup

    

    # ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

    verify_admin(x_admin_password)

    

    # ÃÂ§ÃÂÃÂ½ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂªÃÂ¥ÃÂÃÂÃÂ¨ÃÂ®ÃÂ¸ÃÂ¥ÃÂ­ÃÂÃÂ¦ÃÂ¯ÃÂÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ­ÃÂÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂÃÂÃÂ§ÃÂºÃÂ¿ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂ­ÃÂ¦ÃÂ¨ÃÂªÃÂ§ÃÂºÃÂ¿

    if not re.match(r'^[\w\-]+\.db$', filename):

        raise HTTPException(status_code=400, detail="ÃÂ¦ÃÂÃÂ ÃÂ¦ÃÂÃÂÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂÃÂ")

    

    if restore_backup(filename):

        return {"success": True, "message": "ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¥ÃÂÃÂ"}

    raise HTTPException(status_code=400, detail="ÃÂ¨ÃÂ¿ÃÂÃÂ¥ÃÂÃÂÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥")



@app.delete("/api/admin/backup/{filename}")

async def admin_delete_backup(filename: str, x_admin_password: str = Header(None)):

    """ÃÂ¥ÃÂÃÂ ÃÂ©ÃÂÃÂ¤ÃÂ¦ÃÂÃÂÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂ¤ÃÂÃÂ¤ÃÂ»ÃÂ½"""

    import re

    from backend.backup import delete_backup

    

    # ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?

    verify_admin(x_admin_password)

    

    # ÃÂ§ÃÂÃÂ½ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂªÃÂ¥ÃÂÃÂÃÂ¨ÃÂ®ÃÂ¸ÃÂ¥ÃÂ­ÃÂÃÂ¦ÃÂ¯ÃÂÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ­ÃÂÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂÃÂÃÂ§ÃÂºÃÂ¿ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂ­ÃÂ¦ÃÂ¨ÃÂªÃÂ§ÃÂºÃÂ¿

    if not re.match(r'^[\w\-]+\.db$', filename):

        raise HTTPException(status_code=400, detail="ÃÂ¦ÃÂÃÂ ÃÂ¦ÃÂÃÂÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂÃÂ")

    

    if delete_backup(filename):

        return {"success": True}

    raise HTTPException(status_code=400, detail="ÃÂ¥ÃÂÃÂ ÃÂ©ÃÂÃÂ¤ÃÂ¥ÃÂ¤ÃÂ±ÃÂ¨ÃÂ´ÃÂ¥")



# ============ ÃÂ©ÃÂ¡ÃÂµÃÂ©ÃÂÃÂ¢ÃÂ¨ÃÂ·ÃÂ¯ÃÂ§ÃÂÃÂ± ============



@app.get("/")

async def index():

    """ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ°ÃÂ©ÃÂ¦ÃÂÃÂ©ÃÂ¡ÃÂµ"""

    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))



@app.get("/admin")

async def admin_page():

    """ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂ°ÃÂ§ÃÂ®ÃÂ¡ÃÂ§ÃÂÃÂÃÂ¯ÃÂ¿ÃÂ½?""

    return FileResponse(os.path.join(FRONTEND_DIR, 'admin.html'))



@app.get("/uploads/{filename}")

async def serve_upload(filename: str):

    """ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ¾ÃÂÃÂ¤ÃÂ¸ÃÂÃÂ¤ÃÂ¼ÃÂ ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶"""

    import re

    # ÃÂ§ÃÂÃÂ½ÃÂ¥ÃÂÃÂÃÂ¥ÃÂÃÂÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¯ÃÂ¼ÃÂÃÂ¥ÃÂÃÂªÃÂ¥ÃÂÃÂÃÂ¨ÃÂ®ÃÂ¸ÃÂ¥ÃÂ­ÃÂÃÂ¦ÃÂ¯ÃÂÃÂ¦ÃÂÃÂ°ÃÂ¥ÃÂ­ÃÂÃÂ£ÃÂÃÂÃÂ§ÃÂÃÂ¹ÃÂ¥ÃÂÃÂÃÂ§ÃÂÃÂ­ÃÂ¦ÃÂ¨ÃÂªÃÂ§ÃÂºÃÂ¿

    if not re.match(r'^[\w\.-]+$', filename):

        raise HTTPException(status_code=400, detail="ÃÂ¦ÃÂÃÂ ÃÂ¦ÃÂÃÂÃÂ§ÃÂÃÂÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¥ÃÂÃÂ")

    

    safe_path = os.path.join(UPLOADS_DIR, filename)

    # ÃÂ©ÃÂªÃÂÃÂ¨ÃÂ¯ÃÂÃÂ¨ÃÂ·ÃÂ¯ÃÂ¥ÃÂ¾ÃÂÃÂ§ÃÂ¡ÃÂ®ÃÂ¥ÃÂ®ÃÂÃÂ¥ÃÂÃÂ¨UPLOADS_DIRÃÂ¯ÃÂ¿ÃÂ½?

    if not os.path.realpath(safe_path).startswith(os.path.realpath(UPLOADS_DIR)):

        raise HTTPException(status_code=403, detail="ÃÂ§ÃÂ¦ÃÂÃÂ¦ÃÂ­ÃÂ¢ÃÂ¨ÃÂ®ÃÂ¿ÃÂ©ÃÂÃÂ®")

    

    if not os.path.exists(safe_path):

        raise HTTPException(status_code=404, detail="ÃÂ¦ÃÂÃÂÃÂ¤ÃÂ»ÃÂ¶ÃÂ¤ÃÂ¸ÃÂÃÂ¥ÃÂ­ÃÂÃÂ¯ÃÂ¿ÃÂ½?)

    

    return FileResponse(safe_path)



if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

