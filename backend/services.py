import os
import uuid
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from backend.database import get_db
from backend.models import *

# ============ 审核规则常量 ============
# 一张图片需要的最少投票人数（3人投票制）
REQUIRED_VOTES = 3

# ============ 审核状态常量 ============
# 集中定义审核状态，避免多处硬编码
REVIEW_STATUS_PASS = 'pass'
REVIEW_STATUS_FAIL = 'fail'
REVIEW_STATUS_SKIP = 'skip'
REVIEW_STATUS_DISPUTED = 'disputed'  # 有争议（3人意见不一致）
REVIEW_STATUSES = (REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP, REVIEW_STATUS_DISPUTED)

# 管理员密码文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD_FILE = os.path.join(BASE_DIR, 'data', 'admin_password.txt')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

def get_admin_password():
    """获取管理员密码 - 读取现有密码，否则生成新密码"""
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'r') as f:
            saved_password = f.read().strip()
            if saved_password:
                return saved_password
    # 生成新密码
    password = str(uuid.uuid4())[:8].upper()
    os.makedirs(os.path.dirname(PASSWORD_FILE), exist_ok=True)
    with open(PASSWORD_FILE, 'w') as f:
        f.write(password)
    return password

def log_message(message: str):
    """记录日志到文件"""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f'app_{datetime.now().strftime("%Y%m%d")}.log')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")

# ============ 用户服务 ============

def create_or_get_user(user_id: str, nickname: str = "匿名用户") -> UserResponse:
    """创建或获取用户"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 检查用户是否存在
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        # 创建新用户
        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO users (id, nickname, created_at, last_active) VALUES (?, ?, ?, ?)",
            (user_id, nickname, now, now)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
    
    # 获取用户审核数量
    cursor.execute("SELECT COUNT(*) as count FROM reviews WHERE user_id = ?", (user_id,))
    total_reviews = cursor.fetchone()['count']
    
    conn.close()
    
    return UserResponse(
        id=user['id'],
        nickname=user['nickname'],
        created_at=user['created_at'],
        last_active=user['last_active'],
        is_banned=user['is_banned'],
        total_reviews=total_reviews
    )

def update_user_nickname(user_id: str, nickname: str) -> bool:
    """更新用户昵称"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user_id))
    conn.commit()
    conn.close()
    return True

def update_user_activity(user_id: str):
    """更新用户最后活跃时间"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_active = ? WHERE id = ?", 
                   (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def get_all_users(sort_by: str = "id") -> List[UserResponse]:
    """获取所有用户"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 安全：ORDER BY 注入 - 严格白名单验证
    # order_by 值由白名单控制，确保安全
    allowed_sort = {
        "id": "u.id",
        "total_reviews": "review_count",
        "last_active": "u.last_active"
    }
    order_by = allowed_sort.get(sort_by, "u.id")
    
    cursor.execute(f'''
        SELECT u.id, u.nickname, u.created_at, u.last_active, u.is_banned, COUNT(r.id) as review_count
        FROM users u
        LEFT JOIN reviews r ON u.id = r.user_id
        GROUP BY u.id
        ORDER BY {order_by} DESC, u.id ASC
    ''')
    
    users = []
    for row in cursor.fetchall():
        users.append(UserResponse(
            id=row['id'],
            nickname=row['nickname'],
            created_at=row['created_at'],
            last_active=row['last_active'],
            is_banned=row['is_banned'],
            total_reviews=row['review_count']
        ))
    
    conn.close()
    return users

def ban_user(user_id: str, banned: bool = True):
    """封禁/解封用户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = ? WHERE id = ?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()

def clear_user_reviews(user_id: str):
    """清除用户的所有审核结果"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ============ 角色服务 ============

def create_role(name: str, image_path: str, avatar_path: str = None) -> RoleResponse:
    """创建角色"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO roles (name, image_path, avatar_path) VALUES (?, ?, ?)",
            (name, image_path, avatar_path)
        )
        role_id = cursor.lastrowid
        conn.commit()
        
        # 扫描并添加图片
        scan_and_add_images(role_id, image_path)
        
        cursor.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
        role = cursor.fetchone()
        conn.close()
        
        return RoleResponse(
            id=role['id'],
            name=role['name'],
            image_path=role['image_path'],
            avatar_path=role['avatar_path']
        )
    except Exception as e:
        conn.close()
        raise e

def get_all_roles() -> List[RoleResponse]:
    """获取所有角色（优化：使用JOIN一次性查询，新投票规则）"""

    conn = get_db()
    cursor = conn.cursor()

    # 新投票规则：统计3人全部通过的图片数量
    cursor.execute("""
        SELECT 
            r.id, r.name, r.image_path, r.avatar_path,
            COUNT(DISTINCT i.id) as total_images,
            COALESCE((
                SELECT COUNT(*) FROM (
                    SELECT rev.image_id
                    FROM reviews rev
                    JOIN images img ON rev.image_id = img.id
                    WHERE img.role_id = r.id
                    AND rev.status != 'skip'
                    GROUP BY rev.image_id
                    HAVING COUNT(*) >= ? AND SUM(CASE WHEN rev.status = 'pass' THEN 1 ELSE 0 END) = COUNT(*)
                ) AS completed
            ), 0) as completed_images
        FROM roles r
        LEFT JOIN images i ON r.id = i.role_id
        GROUP BY r.id
    """, (REQUIRED_VOTES,))

    roles = []
    for row in cursor.fetchall():
        completed_images = row['completed_images'] or 0
        roles.append(RoleResponse(
            id=row['id'],
            name=row['name'],
            image_path=row['image_path'],
            avatar_path=row['avatar_path'],
            total_images=row['total_images'] or 0,
            reviewed_images=completed_images,
            pass_count=completed_images,
            fail_count=0
        ))

    conn.close()
    return roles


def delete_role(role_id: int):
    """删除角色"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM images WHERE role_id = ?", (role_id,))
    cursor.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()
    conn.close()

def refresh_role_images(role_id: int):
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
            # 使用 executemany 批量删除，避免多次往返数据库，同时使用参数化查询防止注入
            cursor.executemany(
                "DELETE FROM reviews WHERE image_id = ?",
                [(img_id,) for img_id in validated_ids],
            )
    
    # 删除旧图片记录
    cursor.execute("DELETE FROM images WHERE role_id = ?", (role_id,))
    conn.commit()
    conn.close()
    
    # 重新扫描（在新连接中执行，避免阻塞）
    scan_and_add_images(role_id, image_path)
    
    log_message(f"刷新角色 {role_id} 完成")
    return True

# ============ 图片服务 ============

def scan_and_add_images(role_id: int, base_path: str):
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
    
    return added_count

def get_image_for_review(user_id: str, role_id: Optional[int] = None) -> Optional[ImageResponse]:
    """获取待审核图片"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 使用 NOT EXISTS 替代 NOT IN，利用索引优化
    params = [user_id, REVIEW_STATUS_SKIP, REVIEW_STATUS_SKIP, REQUIRED_VOTES]
    
    sql = f'''
        SELECT i.*, r.name as role_name
        FROM images i
        LEFT JOIN roles r ON i.role_id = r.id
        WHERE NOT EXISTS (
            SELECT 1 FROM reviews 
            WHERE image_id = i.id AND user_id = ? AND status != ?
        )
            AND (
            SELECT COUNT(*) FROM reviews 
            WHERE image_id = i.id AND status != ?
        ) < ?
    '''
    if role_id:
        sql = f'''
            SELECT i.*, r.name as role_name
            FROM images i
            LEFT JOIN roles r ON i.role_id = r.id
            WHERE i.role_id = ? AND NOT EXISTS (
                SELECT 1 FROM reviews 
                WHERE image_id = i.id AND user_id = ? AND status != ?
            )
            AND (
                SELECT COUNT(*) FROM reviews 
                WHERE image_id = i.id AND status != ?
            ) < ?
            '''
        params = [role_id, user_id, REVIEW_STATUS_SKIP, REVIEW_STATUS_SKIP, REQUIRED_VOTES]
    
    cursor.execute(sql + ' ORDER BY RANDOM() LIMIT 1', params)
    
    row = cursor.fetchone()
    
    if row:
        # 统计审核情况
        cursor.execute('''
            SELECT status, COUNT(*) as count FROM reviews
            WHERE image_id = ? AND status != ?
            GROUP BY status
        ''', (row['id'], REVIEW_STATUS_SKIP))
        stats = {s['status']: s['count'] for s in cursor.fetchall()}
        
        # 检查用户是否已审核
        cursor.execute(
            "SELECT status FROM reviews WHERE image_id = ? AND user_id = ?",
            (row['id'], user_id)
        )
        user_review = cursor.fetchone()
        
        conn.close()
        
        return ImageResponse(
            id=row['id'],
            path=row['path'],
            role_id=row['role_id'],
            role_name=row['role_name'],
            review_count=sum(stats.values()),
            pass_count=stats.get('pass', 0),
            fail_count=stats.get('fail', 0),
            skip_count=stats.get('skip', 0),
            is_reviewed_by_user=user_review['status'] if user_review else None
        )
    
    conn.close()
    return None

def submit_review(image_id: int, user_id: str, status: str):
    """提交审核结果"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT OR REPLACE INTO reviews (image_id, user_id, status, reviewed_at) VALUES (?, ?, ?, ?)",
        (image_id, user_id, status, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_user_reviews(user_id: str) -> List[dict]:
    """获取用户的审核记录"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.*, i.path as image_path
        FROM reviews r
        JOIN images i ON r.image_id = i.id
        WHERE r.user_id = ?
        ORDER BY r.reviewed_at DESC
    ''', (user_id,))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'id': row['id'],
            'image_id': row['image_id'],
            'image_path': row['image_path'],
            'status': row['status'],
            'reviewed_at': row['reviewed_at']
        })
    
    conn.close()
    return results

def delete_review(review_id: int):
    """删除审核记录"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()

# ============ 统计服务 ============

def get_overall_stats() -> StatsResponse:
    """获取总体统计"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM images")
    total_images = cursor.fetchone()['count'] or 0
    
    # 使用单个聚合查询获取所有统计数据
    # vote_count 只计算非 skip 的评审，用于判断完成度
    # pass_count/fail_count/skip_count 计算所有状态
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT CASE WHEN vote_count > 0 THEN image_id END) as reviewed_images,
            SUM(pass_count) as pass_count,
            SUM(fail_count) as fail_count,
            SUM(skip_count) as skip_count,
            SUM(vote_count) as total_reviews,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count = 0 THEN image_id END) as completed_images
        FROM (
            SELECT 
                image_id,
                COUNT(CASE WHEN status != ? THEN 1 END) as vote_count,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as pass_count,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as fail_count,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as skip_count
            FROM reviews
            GROUP BY image_id
        )
    ''', (REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP))
    
    stats = cursor.fetchone()
    conn.close()
    
    total_reviews = stats['total_reviews'] or 0
    completed_images = stats['completed_images'] or 0
    progress_percent = (total_reviews / (total_images * REQUIRED_VOTES) * 100) if total_images > 0 else 0
    
    return StatsResponse(
        total_images=total_images,
        reviewed_images=stats['reviewed_images'] or 0,
        total_reviews=total_reviews,
        pass_count=stats['pass_count'] or 0,
        fail_count=stats['fail_count'] or 0,
        skip_count=stats['skip_count'] or 0,
        progress_percent=round(progress_percent, 2),
        completed_images=completed_images
    )

def get_role_stats(role_id: int) -> Optional[StatsResponse]:
    """获取角色统计"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM images WHERE role_id = ?", (role_id,))
    total_images = cursor.fetchone()['count']
    
    # 使用聚合查询（与 get_overall_stats 保持一致）
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT image_id) as reviewed_images,
            SUM(pass_count) as pass_count,
            SUM(fail_count) as fail_count,
            SUM(skip_count) as skip_count,
            SUM(vote_count) as total_reviews,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count = 0 THEN image_id END) as completed_images
        FROM (
            SELECT 
                r.image_id,
                COUNT(CASE WHEN r.status != ? THEN 1 END) as vote_count,
                SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) as pass_count,
                SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) as fail_count,
                SUM(CASE WHEN r.status = ? THEN 1 ELSE 0 END) as skip_count
            FROM reviews r
            JOIN images i ON r.image_id = i.id
            WHERE i.role_id = ?
            GROUP BY r.image_id
        )
    """, (REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP, role_id))
    
    stats = cursor.fetchone()
    conn.close()
    
    if total_images == 0:
        return None
    
    total_reviews = stats["total_reviews"] or 0
    completed_images = stats["completed_images"] or 0
    progress_percent = (total_reviews / (total_images * REQUIRED_VOTES) * 100) if total_images > 0 else 0
    
    return StatsResponse(
        total_images=total_images,
        reviewed_images=stats["reviewed_images"] or 0,
        total_reviews=total_reviews,
        pass_count=stats["pass_count"] or 0,
        fail_count=stats["fail_count"] or 0,
        skip_count=stats["skip_count"] or 0,
        progress_percent=round(progress_percent, 2),
        completed_images=completed_images
    )

def get_image_final_status(image_id: int) -> Optional[str]:
    """获取图片最终审核状态
    - 3人投票全部通过 = pass
    - 3人投票有分歧（有通过也有不通过）= disputed
    - 3人投票全部不通过 = fail
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT status FROM reviews
        WHERE image_id = ? AND status != ?
        ORDER BY reviewed_at ASC, id ASC
        LIMIT ?
    ''', (image_id, REVIEW_STATUS_SKIP, REQUIRED_VOTES))
    
    votes = [row['status'] for row in cursor.fetchall()]
    conn.close()
    
    return _calculate_final_status(votes)




def _calculate_final_status(votes):
    """Helper: Calculate final status from votes list.
    Shared logic between single and batch functions.
    """
    if len(votes) < REQUIRED_VOTES:
        return None
    pass_count = votes.count(REVIEW_STATUS_PASS)
    fail_count = votes.count(REVIEW_STATUS_FAIL)
    if pass_count == REQUIRED_VOTES:
        return REVIEW_STATUS_PASS
    elif fail_count == REQUIRED_VOTES:
        return REVIEW_STATUS_FAIL
    else:
        return REVIEW_STATUS_DISPUTED


def get_image_final_statuses_batch(image_ids):
    """Batch get final status for multiple images.
    Returns: {image_id: status} dict, None means review not completed.
    """
    if not image_ids:
        return {}
    
    # Validate and normalize all IDs to integers, then deduplicate
    validated_ids = []
    skipped_ids = []
    seen_ids = set()
    for img_id in image_ids:
        try:
            int_id = int(img_id)
            if int_id not in seen_ids:
                validated_ids.append(int_id)
                seen_ids.add(int_id)
        except (TypeError, ValueError):
            skipped_ids.append(img_id)
    
    if skipped_ids:
        log_message(f"Skipped invalid image IDs: {skipped_ids}")
    
    if not validated_ids:
        return {}
    conn = get_db()
    try:
        cursor = conn.cursor()
        # Chunk validated_ids to avoid SQLite parameter limits
        batch_size = 800
        all_votes = []
        for i in range(0, len(validated_ids), batch_size):
            batch_ids = validated_ids[i:i + batch_size]
            placeholders = ','.join('?' * len(batch_ids))
            # Note: placeholders is safe (just '?' repeated), actual values use parameterized query
            sql = (
                'SELECT image_id, status FROM reviews '
                'WHERE image_id IN (' + placeholders + ') '
                'AND status != ? '
                'ORDER BY image_id, reviewed_at ASC, id ASC'
            )
            cursor.execute(sql, (*batch_ids, REVIEW_STATUS_SKIP))
            all_votes.extend(cursor.fetchall())
    finally:
        conn.close()
    # Group votes by image and limit to REQUIRED_VOTES per image
    votes_by_image = {}
    for row in all_votes:
        img_id = row['image_id']
        if img_id not in votes_by_image:
            votes_by_image[img_id] = []
        # Limit votes per image to match single-query behavior
        if len(votes_by_image[img_id]) < REQUIRED_VOTES:
            votes_by_image[img_id].append(row['status'])
    
    # Calculate final status for each image using shared helper
    result = {}
    for img_id in validated_ids:
        votes = votes_by_image.get(img_id, [])
        result[img_id] = _calculate_final_status(votes)
    return result

def get_disputed_images() -> List[dict]:
    """获取所有有争议的图片"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 找出有分歧的图片（不是全部通过，也不是全部不通过）
    cursor.execute('''
        SELECT DISTINCT i.id, i.path, i.role_id, r.name as role_name
        FROM images i
        LEFT JOIN roles r ON i.role_id = r.id
        WHERE EXISTS (
            SELECT 1 FROM reviews rev
            WHERE rev.image_id = i.id AND rev.status = 'pass'
        )
        AND EXISTS (
            SELECT 1 FROM reviews rev
            WHERE rev.image_id = i.id AND rev.status = 'fail'
        )
        ORDER BY i.id DESC
    ''')
    
    images = []
    for row in cursor.fetchall():
        images.append({
            'id': row['id'],
            'path': row['path'],
            'role_id': row['role_id'],
            'role_name': row['role_name']
        })
    
    conn.close()
    return images

# ============

# ============ 设置服务 ============

def get_setting(key: str) -> Optional[str]:
    """获取单个设置"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def save_setting(key: str, value: str):
    """保存设置"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()

def get_settings() -> dict:
    """获取所有设置"""
    return {
        "title": get_setting("title") or "图片审核系统",
        "icon": get_setting("icon") or "",
        "review_rule": get_setting("review_rule") or "",
        "auto_backup_time": get_setting("auto_backup_time") or "03:00",
        "auto_backup_enabled": get_setting("auto_backup_enabled") or "true",
        "backup_retention_days": get_setting("backup_retention_days") or "7"
    }

def get_settings_all() -> dict:
    """获取所有设置（后台用）"""
    return get_settings()

def get_review_rule() -> dict:
    """获取审核规则"""
    return {
        "content": get_setting("review_rule") or "# 暂无审核要求\n\n请在后台配置审核要求。"
    }

# ============ 备份设置服务 ============

def get_auto_backup_time() -> str:
    """获取自动备份时间"""
    return get_setting("auto_backup_time") or "03:00"

def get_auto_backup_enabled() -> bool:
    """获取自动备份是否启用"""
    value = get_setting("auto_backup_enabled")
    return value != "false"  # 默认启用

def get_backup_retention_days() -> int:
    """获取备份保留天数"""
    try:
        return int(get_setting("backup_retention_days") or "7")
    except (ValueError, TypeError) as e:
        log_message(f"获取备份保留天数失败: {str(e)}, 使用默认值7")
        return 7

def get_last_backup_date() -> str:
    """获取上次备份日期"""
    return get_setting("last_backup_date") or ""

def set_last_backup_date(date_str: str):
    """设置上次备份日期"""
    save_setting("last_backup_date", date_str)
