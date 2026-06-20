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

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Response, Query
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

def release_download_slot(user_id: str):
    """释放下载槽位"""
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon(lambda: asyncio.ensure_future(_release_and_next(user_id)))
    except RuntimeError:
        pass

async def _release_and_next(user_id: str):
    """释放当前用户的槽位"""
    async with queue_lock:
        current = user_active_downloads.get(user_id, 0)
        if current > 0:
            user_active_downloads[user_id] = current - 1

# 初始化 - 支持直接运行和模块运行
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
os.makedirs(UPLOADS_DIR, exist_ok=True)
THUMBNAIL_CACHE_DIR = os.path.join(BASE_DIR, 'data', 'thumbnails')
SERVER_START_TIME = time.time()
os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)

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
    from backend.database import migrate_add_credibility
    migrate_add_credibility()
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
    
    # 获取下一张预加载图片ID（确定性排序）
    next_id = get_next_image_id(user_id, role_id, image.id if image else None)
    
    return {"image": image, "next_image_id": next_id}

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
            release_download_slot(user_id)
    else:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
        image = cursor.fetchone()
        conn.close()
        if not image:
            raise HTTPException(status_code=404, detail="图片不存在")
        return FileResponse(image['path'])



def _compress_image(img, max_size=500*1024, initial_quality=85, quality_step=10,
                       min_quality=20, min_width=200, max_iterations=15):
    """压缩图片到指定大小限制内。
    
    Args:
        img: PIL Image对象（不会修改原图）
        max_size: 最大文件大小（字节），默认500KB
        initial_quality: 初始压缩质量，默认85
        quality_step: 质量递减步长，默认10
        min_quality: 最低质量阈值，默认20
        min_width: 最小宽度阈值，默认200px
        max_iterations: 最大迭代次数，默认15
    
    Returns:
        bytes: 压缩后的JPEG字节数据
    """
    # 在副本上操作，避免修改原图
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
        
        # 记录当前最佳结果
        if size < best_size:
            best_bytes = data
            best_size = size
        
        # 达到质量下限，先尝试缩小尺寸
        if quality <= min_quality and img.size[0] > min_width:
            new_size = (int(img.size[0] * 0.75), int(img.size[1] * 0.75))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            quality = min(quality + quality_step, 70) if iterations > 3 else quality
            continue
        
        # 降低质量
        if quality > min_quality:
            quality -= quality_step
        elif img.size[0] > min_width:
            new_size = (int(img.size[0] * 0.75), int(img.size[1] * 0.75))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        else:
            break
    
    # 如果所有迭代都无法满足大小要求，返回最佳结果
    if best_bytes is not None:
        return best_bytes
    
    # 最终兜底：强制使用最低质量
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=min_quality, optimize=True)
    return output.getvalue()


@app.get("/api/image/{image_id}/thumbnail")
async def get_thumbnail(image_id: int):
    """获取压缩缩略图，确保文件小于500KB"""
    # 检查缓存
    cache_key = f"{image_id}.jpg"
    cache_path = os.path.join(THUMBNAIL_CACHE_DIR, cache_key)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                cached_data = f.read()
            return StreamingResponse(
                io.BytesIO(cached_data),
                media_type="image/jpeg"
            )
        except Exception:
            pass  # 缓存读取失败，继续生成

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM images WHERE id = ?", (image_id,))
    image = cursor.fetchone()
    conn.close()

    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    original_path = image['path']

    try:
        with Image.open(original_path) as img:
            # 转换为 RGB（处理 PNG 透明通道等）
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')

            # 计算缩放比例
            width, height = img.size
            if width > THUMBNAIL_MAX_SIZE or height > THUMBNAIL_MAX_SIZE:
                ratio = min(THUMBNAIL_MAX_SIZE / width, THUMBNAIL_MAX_SIZE / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 压缩到500KB以内
            compressed_data = _compress_image(img)

            # 保存到缓存
            try:
                with open(cache_path, 'wb') as f:
                    f.write(compressed_data)
            except Exception:
                pass  # 缓存写入失败不影响返回

            return StreamingResponse(
                io.BytesIO(compressed_data),
                media_type="image/jpeg"
            )

    except Exception:
        # 记录缩略图处理失败的异常，避免静默失败
        logger.exception("缩略图生成失败 %s, 返回原图", original_path)
        return FileResponse(original_path)

@app.get("/api/stats")
async def get_stats():
    """获取统计数据"""
    return get_overall_stats()

@app.get("/api/user-stats")
async def get_user_stats(user_id: str = Query(None)):
    """获取当前用户审核数"""
    if not user_id:
        return {"total_reviews": 0, "completed_reviews": 0}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(CASE WHEN status != 'skip' THEN 1 END) as total_reviews FROM reviews WHERE user_id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return {
        "total_reviews": result['total_reviews'] if result else 0,
        "completed_reviews": result['total_reviews'] if result else 0
    }

@app.get("/api/roles")
async def get_roles():
    """获取所有角色"""
    return get_all_roles()

@app.get("/api/admin/disputed-images")
async def admin_get_disputed_images(x_admin_password: str = Header(None)):
    """获取所有有争议的图片（需要管理员权限）"""
    verify_admin(x_admin_password)
    return get_disputed_images()

@app.get("/api/settings")
async def get_all_settings():
    """获取所有设置"""
    return get_settings()

@app.get("/api/settings/review-rule")
async def get_review_rule_api():
    """获取审核规则"""
    return {"content": get_setting("review_rule") or ""}

@app.get("/api/image/next-id")
async def get_next_id(user_id: str, current_id: int, role_id: Optional[int] = None):
    """获取下一张待审核图片ID（随机排序，用于预加载）
    同时返回当前图片(current_id)的角色名
    """
    from backend.database import get_db
    next_id = get_next_image_id(user_id, role_id, current_id)
    
    current_role_name = None
    next_role_name = None
    
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 获取当前图片的角色名（用于徽标显示）
        cursor.execute("SELECT r.name FROM images i JOIN roles r ON i.role_id = r.id WHERE i.id = ?", (current_id,))
        row = cursor.fetchone()
        if row:
            current_role_name = row[0]
        
        # 获取下一张图片的角色名
        if next_id:
            cursor.execute("SELECT r.name FROM images i JOIN roles r ON i.role_id = r.id WHERE i.id = ?", (next_id,))
            row = cursor.fetchone()
            if row:
                next_role_name = row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    
    return {"next_image_id": next_id, "role_name": current_role_name, "next_role_name": next_role_name}


@app.get("/api/settings/notice")
async def get_notice():
    """获取公告内容"""
    return {"content": get_setting("notice") or "", "version": get_setting("notice_version") or "0"}

@app.get("/api/settings/title")
async def get_title():
    """获取页面标题"""
    return {"title": get_setting("title") or "图片审核系统"}

@app.get("/api/settings/votes")
async def get_votes_config():
    """获取投票配置"""
    from backend.services import REQUIRED_VOTES
    return {"required_votes": REQUIRED_VOTES}

@app.get("/api/settings/icon")
async def get_icon():
    """获取页面图标"""
    return {"icon": get_setting("icon") or ""}

# ============ 后台API ============

@app.get("/api/admin/verify")
async def verify_admin_password(x_admin_password: str = Header(None)):
    """验证管理员密码"""
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
    """创建角色"""
    verify_admin(x_admin_password)
    
    avatar_path = None
    if avatar:
        # 安全：检查文件大小
        avatar_content = await avatar.read()
        if len(avatar_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件过大，最大5MB")
        
        # 安全：只提取文件名，防止路径遍历
        safe_filename = os.path.basename(avatar.filename)
        filename = f"{uuid.uuid4()}_{safe_filename}"
        avatar_path = os.path.join(UPLOADS_DIR, filename)
        with open(avatar_path, 'wb') as f:
            f.write(avatar_content)
    
    role = create_role(name, image_path, avatar_path)
    log_message(f"创建角色: {name} (路径: {image_path})")
    return role

@app.get("/api/admin/roles")
async def admin_get_roles(x_admin_password: str = Header(None)):
    """获取所有角色"""
    verify_admin(x_admin_password)
    return get_all_roles()

@app.post("/api/admin/roles/{role_id}/refresh")
async def admin_refresh_role(role_id: int, x_admin_password: str = Header(None)):
    """刷新角色图片"""
    verify_admin(x_admin_password)
    # 使用线程池执行器避免阻塞事件循环
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, refresh_role_images, role_id)
    if success:
        log_message(f"刷新角色 {role_id} 图片成功")
        return {"success": True}
    else:
        log_message(f"刷新角色 {role_id} 图片失败")
        return {"success": False, "error": "刷新失败，可能是角色不存在或路径无效"}

@app.put("/api/admin/roles/{role_id}")
async def admin_update_role(
    role_id: int,
    name: str = Form(...),
    image_path: str = Form(...),
    refresh_images: str = Form(None),
    avatar: UploadFile = File(None),
    x_admin_password: str = Header(None)
):
    """修改角色"""
    verify_admin(x_admin_password)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 获取当前角色信息
    cursor.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    role = cursor.fetchone()
    
    if not role:
        conn.close()
        raise HTTPException(status_code=404, detail="角色不存在")
    
    avatar_path = role['avatar_path']
    
    # 处理新头像 - 安全处理文件名和大小
    if avatar and avatar.filename:
        avatar_content = await avatar.read()
        if len(avatar_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件过大，最大5MB")
        
        safe_filename = os.path.basename(avatar.filename)
        filename = f"{uuid.uuid4()}_{safe_filename}"
        avatar_path = os.path.join(UPLOADS_DIR, filename)
        with open(avatar_path, 'wb') as f:
            f.write(avatar_content)
    
    # 更新角色信息
    cursor.execute(
        "UPDATE roles SET name = ?, image_path = ?, avatar_path = ? WHERE id = ?",
        (name, image_path, avatar_path, role_id)
    )
    conn.commit()
    
    # 如果需要刷新图片，使用线程池执行器避免阻塞
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
    return {"success": True}

@app.delete("/api/admin/roles/{role_id}")
async def admin_delete_role(role_id: int, x_admin_password: str = Header(None)):
    """删除角色"""
    verify_admin(x_admin_password)
    delete_role(role_id)
    log_message(f"删除角色 {role_id}")
    return {"success": True}

@app.get("/api/admin/users")
async def admin_get_users(sort_by: str = "id", x_admin_password: str = Header(None)):
    """获取所有用户"""
    verify_admin(x_admin_password)
    return get_all_users(sort_by)

@app.post("/api/admin/credibility/recalc")
async def admin_recalc_credibility(x_admin_password: str = Header(None)):
    """全量重新计算所有用户可信度"""
    verify_admin(x_admin_password)
    from backend.database import update_all_credibility
    update_all_credibility()
    return {"success": True, "message": "可信度已重新计算"}


@app.get("/api/admin/credibility")
async def admin_credibility(x_admin_password: str = Header(None)):
    """获取所有用户可信度"""
    verify_admin(x_admin_password)
    from backend.services import get_all_credibility
    return {"users": get_all_credibility()}


@app.get("/api/admin/users/daily-stats")
async def admin_users_daily_stats(x_admin_password: str = Header(None)):
    """获取用户每日活跃/新增统计（近30天）"""
    verify_admin(x_admin_password)
    from datetime import datetime, timedelta
    from backend.database import get_db

    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]

    active_counts = {}
    new_counts = {}

    for d in dates:
        active_counts[d] = 0
        new_counts[d] = 0

    # Count daily active users (by last_active)
    cursor.execute("SELECT last_active FROM users")
    for row in cursor.fetchall():
        try:
            day = row[0][:10]  # "2026-06-19T..." -> "2026-06-19"
            if day in active_counts:
                active_counts[day] += 1
        except Exception:
            pass

    # Count new users daily (by created_at)
    cursor.execute("SELECT created_at FROM users")
    for row in cursor.fetchall():
        try:
            day = row[0][:10]
            if day in new_counts:
                new_counts[day] += 1
        except Exception:
            pass

    conn.close()

    return {
        "dates": dates,
        "active": [active_counts[d] for d in dates],
        "new_users": [new_counts[d] for d in dates],
    }


@app.get("/api/admin/users/{user_id}/reviews")
async def admin_get_user_reviews(user_id: str, x_admin_password: str = Header(None)):
    """获取用户审核记录"""
    verify_admin(x_admin_password)
    return get_user_reviews(user_id)

@app.delete("/api/admin/reviews/{review_id}")
async def admin_delete_review(review_id: int, x_admin_password: str = Header(None)):
    """删除审核记录"""
    verify_admin(x_admin_password)
    delete_review(review_id)
    return {"success": True}

@app.delete("/api/admin/users/{user_id}/reviews")
async def admin_clear_user_reviews(user_id: str, x_admin_password: str = Header(None)):
    """清除用户审核记录"""
    verify_admin(x_admin_password)
    clear_user_reviews(user_id)
    log_message(f"清除用户 {user_id} 的所有审核记录")
    return {"success": True}

@app.post("/api/admin/users/{user_id}/ban")
async def admin_ban_user(user_id: str, banned: bool = Form(True), x_admin_password: str = Header(None)):
    """封禁/解封用户"""
    verify_admin(x_admin_password)
    ban_user(user_id, banned)
    log_message(f"用户 {user_id} {'封禁' if banned else '解封'}")
    return {"success": True}

@app.get("/api/admin/stats")
async def admin_get_stats(x_admin_password: str = Header(None)):
    """获取后台统计"""
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
    """导出所有有争议的图片（按角色分文件夹）"""
    verify_admin(x_admin_password)
    
    # 使用服务函数获取争议图片
    disputed_images = get_disputed_images()
    
    if not disputed_images:
        return JSONResponse(content={"message": "暂无可导出图片", "count": 0})
    
    # 创建导出目录
    export_dir = os.path.join(BASE_DIR, 'exports')
    os.makedirs(export_dir, exist_ok=True)
    
    zip_filename = f"争议图片_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(export_dir, zip_filename)
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_count = 0
            
            # 按角色分组
            role_images = {}
            for img in disputed_images:
                role_name = img.get('role_name') or f"角色{img.get('role_id')}"
                if role_name not in role_images:
                    role_images[role_name] = []
                role_images[role_name].append(img)
            
            for role_name, images in role_images.items():
                # 清理角色名称用于文件夹名
                safe_folder_name = "".join(c for c in role_name if c.isalnum() or c in (' ', '-', '_')).strip()
                if not safe_folder_name:
                    safe_folder_name = "未分类"
                
                for img in images:
                    img_path = img['path']
                    if os.path.exists(img_path):
                        arcname = os.path.join(safe_folder_name, os.path.basename(img_path))
                        zipf.write(img_path, arcname)
                        total_count += 1
            
            log_message(f"争议图片导出完成，共 {total_count} 张图片")
        
        return FileResponse(zip_path, filename=zip_filename, media_type='application/zip')
        
    except Exception as e:
        log_message(f"导出失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/settings")
async def admin_get_settings(x_admin_password: str = Header(None)):
    """获取所有设置"""
    verify_admin(x_admin_password)
    return get_settings_all()

@app.put("/api/admin/settings/title")
async def admin_update_title(title: str = Form(...), x_admin_password: str = Header(None)):
    """更新页面标题"""
    verify_admin(x_admin_password)
    save_setting("title", title)
    return {"success": True}

@app.put("/api/admin/settings/icon")
async def admin_update_icon(icon: str = Form(...), x_admin_password: str = Header(None)):
    """更新页面图标"""
    verify_admin(x_admin_password)
    save_setting("icon", icon)
    return {"success": True}

@app.put("/api/admin/settings/notice")
async def admin_update_notice(content: str = Form(...), x_admin_password: str = Header(None)):
    """更新公告"""
    verify_admin(x_admin_password)
    import time
    save_setting("notice", content)
    save_setting("notice_version", str(int(time.time())))
    return {"success": True}

@app.put("/api/admin/settings/review-rule")
async def admin_update_review_rule(content: str = Form(...), x_admin_password: str = Header(None)):
    """更新审核规则"""
    verify_admin(x_admin_password)
    save_setting("review_rule", content)
    return {"success": True}

@app.put("/api/admin/settings/auto-backup-time")
async def admin_update_auto_backup_time(backup_time: str = Form(...), x_admin_password: str = Header(None)):
    """更新自动备份时间"""
    verify_admin(x_admin_password)
    save_setting("auto_backup_time", backup_time)
    log_message(f"更新自动备份时间: {backup_time}")
    return {"success": True}

@app.put("/api/admin/settings/auto-backup-enabled")
async def admin_update_auto_backup_enabled(enabled: str = Form(...), x_admin_password: str = Header(None)):
    """更新自动备份启用状态"""
    verify_admin(x_admin_password)
    save_setting("auto_backup_enabled", enabled.lower())
    log_message(f"更新自动备份启用状态: {enabled}")
    return {"success": True}

@app.put("/api/admin/settings/backup-retention-days")
async def admin_update_backup_retention_days(days: str = Form(...), x_admin_password: str = Header(None)):
    """更新备份保留天数"""
    verify_admin(x_admin_password)
    save_setting("backup_retention_days", days)
    log_message(f"更新备份保留天数: {days}天")
    return {"success": True}

@app.post("/api/admin/backup/now")
async def admin_backup_now(x_admin_password: str = Header(None)):
    """立即执行备份"""
    verify_admin(x_admin_password)
    from backend.backup import create_backup, cleanup_old_backups
    backup_path = create_backup()
    if backup_path:
        cleanup_old_backups(get_backup_retention_days())
        log_message(f"管理员手动触发备份成功")
        return {"success": True, "message": "备份成功", "path": backup_path}
    return {"success": False, "message": "备份失败"}


@app.get("/api/admin/health")
async def admin_health(x_admin_password: str = Header(None)):
    """系统健康检查"""
    verify_admin(x_admin_password)

    import shutil
    import time
    import socket
    import platform
    import sys

    # ---- 数据库检查 ----
    db_ok = True
    db_size = 0
    db_latency = 0
    image_count = 0
    review_count = 0
    user_count = 0
    role_count = 0
    try:
        t0 = time.time()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images")
        image_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM reviews")
        review_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM roles")
        role_count = cursor.fetchone()[0]
        cursor.execute("SELECT sqlite_version()")
        sqlite_ver = cursor.fetchone()[0]
        conn.close()
        db_latency = round((time.time() - t0) * 1000, 1)
        db_path = os.path.join(BASE_DIR, 'data', 'review.db')
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path)
    except Exception as e:
        db_ok = False
        log_message(f"健康检查: 数据库异常 {str(e)}")
        sqlite_ver = "-"

    # ---- 磁盘检查 ----
    try:
        disk = shutil.disk_usage(BASE_DIR)
    except Exception:
        disk = None

    # ---- 目录检查 ----
    dirs = {
        "data": os.path.join(BASE_DIR, "data"),
        "uploads": UPLOADS_DIR,
        "thumbnails": THUMBNAIL_CACHE_DIR,
        "backups": os.path.join(BASE_DIR, "backups"),
    }
    dir_status = {}
    for name, d in dirs.items():
        exists = os.path.exists(d)
        dir_status[name] = {
            "exists": exists,
            "writable": os.access(d, os.W_OK) if exists else False,
            "path": d,
        }

    # ---- 图片文件完整性检查 ----
    missing_images = 0
    total_images = 0
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images")
        total_images = cursor.fetchone()[0]
        # Sample check first 20 images
        cursor.execute("SELECT path FROM images LIMIT 20")
        for row in cursor.fetchall():
            if not os.path.exists(row[0]):
                missing_images += 1
        conn.close()
    except Exception:
        pass

    # ---- 网络检查 ----
    network = {"hostname": socket.gethostname(), "connectivity": True}
    # 尝试解析常见域名检查 DNS/网络
    try:
        socket.getaddrinfo("8.8.8.8", 53, socket.AF_INET, socket.SOCK_STREAM)
        network["dns"] = True
    except Exception:
        network["dns"] = False

    # ---- 系统信息 ----
    uptime_seconds = time.time() - SERVER_START_TIME

    # ---- 内存信息 ----
    memory = {}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                parts = line.split()
                if parts[0] == 'MemTotal:':
                    memory['total'] = int(parts[1]) * 1024
                elif parts[0] == 'MemAvailable:':
                    memory['available'] = int(parts[1]) * 1024
                elif parts[0] == 'SwapTotal:':
                    memory['swap_total'] = int(parts[1]) * 1024
                elif parts[0] == 'SwapFree:':
                    memory['swap_free'] = int(parts[1]) * 1024
        memory['used'] = memory['total'] - memory['available']
        memory['usage_percent'] = round(memory['used'] / memory['total'] * 100, 1) if memory['total'] > 0 else 0
        if memory.get('swap_total', 0) > 0:
            memory['swap_used'] = memory['swap_total'] - memory['swap_free']
            memory['swap_usage_percent'] = round(memory['swap_used'] / memory['swap_total'] * 100, 1)
        else:
            memory['swap_used'] = 0
            memory['swap_usage_percent'] = 0
        memory['total_formatted'] = format_size(memory['total'])
        memory['used_formatted'] = format_size(memory['used'])
        memory['available_formatted'] = format_size(memory['available'])
        memory['swap_total_formatted'] = format_size(memory.get('swap_total', 0))
        memory['swap_used_formatted'] = format_size(memory.get('swap_used', 0))
    except Exception:
        memory = None

    # ---- CPU 信息 ----
    cpu = {}
    try:
        with open('/proc/loadavg') as f:
            parts = f.read().split()
            cpu['load_1min'] = float(parts[0])
            cpu['load_5min'] = float(parts[1])
            cpu['load_15min'] = float(parts[2])
            cpu['cores'] = os.cpu_count() or 0
    except Exception:
        cpu = None

    return {
        "status": "ok" if db_ok else "error",
        "server": {
            "hostname": network["hostname"],
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "uptime": uptime_seconds,
            "uptime_formatted": format_uptime(uptime_seconds),
        },
        "database": {
            "ok": db_ok,
            "latency_ms": db_latency,
            "version": sqlite_ver,
            "size": db_size,
            "size_formatted": format_size(db_size),
            "tables": {
                "images": image_count,
                "reviews": review_count,
                "users": user_count,
                "roles": role_count,
            }
        },
        "storage": {
            "total": disk.total if disk else 0,
            "used": disk.used if disk else 0,
            "free": disk.free if disk else 0,
            "total_formatted": format_size(disk.total) if disk else "-",
            "used_formatted": format_size(disk.used) if disk else "-",
            "free_formatted": format_size(disk.free) if disk else "-",
            "usage_percent": round(disk.used / disk.total * 100, 1) if disk else 0,
        },
        "images": {
            "total": total_images,
            "missing_sample": missing_images,
        },
        "directories": dir_status,
	        "network": network,
	        "memory": memory,
	        "cpu": cpu,
	    }




@app.get("/api/admin/backup/list")
async def admin_list_backups(x_admin_password: str = Header(None)):
    """列出所有备份"""
    verify_admin(x_admin_password)
    from backend.backup import list_backups
    return {"backups": list_backups()}

@app.post("/api/admin/backup/restore/{filename}")
async def admin_restore_backup(filename: str, x_admin_password: str = Header(None)):
    """还原指定备份"""
    import re
    from backend.backup import restore_backup
    
    # 验证管理员权限
    verify_admin(x_admin_password)
    
    # 白名单验证：只允许字母数字下划线和短横线
    if not re.match(r'^[\w\-]+\.db$', filename):
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    if restore_backup(filename):
        return {"success": True, "message": "还原成功"}
    raise HTTPException(status_code=400, detail="还原失败")

@app.delete("/api/admin/backup/{filename}")
async def admin_delete_backup(filename: str, x_admin_password: str = Header(None)):
    """删除指定备份"""
    import re
    from backend.backup import delete_backup
    
    # 验证管理员权限
    verify_admin(x_admin_password)
    
    # 白名单验证：只允许字母数字下划线和短横线
    if not re.match(r'^[\w\-]+\.db$', filename):
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    if delete_backup(filename):
        return {"success": True}
    raise HTTPException(status_code=400, detail="删除失败")

# ============ 页面路由 ============

@app.get("/")
async def index():
    """前台首页"""
    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))

@app.get("/admin")
async def admin_page():
    """后台管理页"""
    return FileResponse(os.path.join(FRONTEND_DIR, 'admin.html'))

@app.get("/uploads/{filename}")
async def serve_upload(filename: str):
    """提供上传文件"""
    import re
    # 白名单验证：只允许字母数字、点和短横线
    if not re.match(r'^[\w\.-]+$', filename):
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    safe_path = os.path.join(UPLOADS_DIR, filename)
    # 验证路径确实在UPLOADS_DIR内
    if not os.path.realpath(safe_path).startswith(os.path.realpath(UPLOADS_DIR)):
        raise HTTPException(status_code=403, detail="禁止访问")
    
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(safe_path)

# ============ 辅助函数 ============

def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if days > 0: parts.append(f"{days}天")
    if hours > 0: parts.append(f"{hours}小时")
    if minutes > 0: parts.append(f"{minutes}分")
    parts.append(f"{secs}秒")
    return "".join(parts)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
