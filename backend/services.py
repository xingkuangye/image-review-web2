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
REQUIRED_WEIGHT = 4.0  # 累计可信度达到此值后判定结果

# ============ 审核状态常量 ============
# 集中定义审核状态，避免多处硬编码
REVIEW_STATUS_PASS = 'pass'
REVIEW_STATUS_FAIL = 'fail'
REVIEW_STATUS_SKIP = 'skip'


def compute_weighted_result(rows, required_weight=None, default_weight=0.5, min_voters=None):
    """
    计算加权审核结果。

    rows: [(user_id, status, credibility_score), ...]
    required_weight: 所需最小总权重，默认 REQUIRED_WEIGHT
    default_weight: credibility_score 为 None 时的默认值
    min_voters: 至少需要多少投票人（仅在可信度计算中使用，用于排除单张图片只有1票的情况）
    返回 'pass'/'fail'/None（权重不足时返回 None）
    """
    if required_weight is None:
        required_weight = REQUIRED_WEIGHT

    unique_voters = len(set(r[0] for r in rows))
    if min_voters is not None and unique_voters < min_voters:
        return None

    w_pass = sum((r[2] if r[2] is not None else default_weight) for r in rows if r[1] == REVIEW_STATUS_PASS)
    w_fail = sum((r[2] if r[2] is not None else default_weight) for r in rows if r[1] == REVIEW_STATUS_FAIL)

    total_weight = w_pass + w_fail
    if total_weight < required_weight:
        return None

    return REVIEW_STATUS_PASS if w_pass >= w_fail else REVIEW_STATUS_FAIL


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
    # 过滤控制字符，防止日志注入
    safe_message = ''.join(c if c.isprintable() or c in '\t\n\r' else '?' for c in message)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {safe_message}\n")

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
        user_token = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO users (id, nickname, created_at, last_active, user_token) VALUES (?, ?, ?, ?, ?)",
            (user_id, nickname, now, now, user_token)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
    
    # 获取用户审核数量
    cursor.execute("SELECT COUNT(*) as count FROM reviews WHERE user_id = ?", (user_id,))
    total_reviews = cursor.fetchone()['count']
    
    # 如果用户没有token，自动生成一个
    token = user['user_token'] if 'user_token' in user else None
    if not token:
        token = str(uuid.uuid4())
        cursor.execute("UPDATE users SET user_token = ? WHERE id = ?", (token, user_id))
        conn.commit()
    
    conn.close()
    
    return UserResponse(
        id=user['id'],
        nickname=user['nickname'],
        created_at=user['created_at'],
        last_active=user['last_active'],
        is_banned=user['is_banned'],
        total_reviews=total_reviews,
        user_token=token
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
    # 验证路径安全
    if not _is_path_safe(image_path):
        raise ValueError("无效的图片路径")
    if avatar_path and not _is_path_safe(avatar_path):
        raise ValueError("无效的头像路径")
    
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
    """获取所有角色（优化：使用JOIN一次性查询）"""

    conn = get_db()
    cursor = conn.cursor()

    # 获取角色基础信息
    cursor.execute("""
        SELECT r.id, r.name, r.image_path, r.avatar_path,
               COUNT(DISTINCT i.id) as total_images
        FROM roles r
        LEFT JOIN images i ON r.id = i.role_id
        GROUP BY r.id
    """)

    role_base = {row['id']: dict(row) for row in cursor.fetchall()}

    # 分别统计通过和失败的数量
    cursor.execute("""
        SELECT img.role_id,
               SUM(CASE WHEN rev.status = 'pass' THEN 1 ELSE 0 END) as pass_count,
               SUM(CASE WHEN rev.status = 'fail' THEN 1 ELSE 0 END) as fail_count
        FROM reviews rev
        JOIN images img ON rev.image_id = img.id
        WHERE rev.status != 'skip'
        GROUP BY img.role_id, rev.image_id
        HAVING COUNT(*) >= ?
    """, (REQUIRED_VOTES,))

    pass_fail_by_role = {}
    for row in cursor.fetchall():
        role_id = row['role_id']
        if role_id not in pass_fail_by_role:
            pass_fail_by_role[role_id] = {'pass': 0, 'fail': 0, 'completed': 0}
        pass_fail_by_role[role_id]['pass'] += row['pass_count']
        pass_fail_by_role[role_id]['fail'] += row['fail_count']
        pass_fail_by_role[role_id]['completed'] += 1

    roles = []
    for role_id, base in role_base.items():
        stats = pass_fail_by_role.get(role_id, {'pass': 0, 'fail': 0, 'completed': 0})
        roles.append(RoleResponse(
            id=role_id,
            name=base['name'],
            image_path=base['image_path'],
            avatar_path=base['avatar_path'],
            total_images=base['total_images'] or 0,
            reviewed_images=stats['completed'],
            pass_count=stats['pass'],
            fail_count=stats['fail']
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

def get_next_image_id(user_id: str, role_id: Optional[int] = None, exclude_id: Optional[int] = None) -> Optional[int]:
    """获取下一张待审核图片ID（确定性排序）"""
    conn = get_db()
    cursor = conn.cursor()
    
    params = [user_id, REVIEW_STATUS_SKIP, REVIEW_STATUS_SKIP, REQUIRED_VOTES]
    
    sql = f'''
        SELECT i.id
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
        sql += ' AND i.role_id = ?'
        params = params + [role_id]
    
    # 随机取一张（排除当前图片）
    if exclude_id:
        all_sql = sql + ' AND i.id != ? ORDER BY RANDOM() LIMIT 1'
        cursor.execute(all_sql, params + [exclude_id])
        row = cursor.fetchone()
        if row:
            conn.close()
            return row[0]
    
    # 无当前图片时随机取第一张
    cursor.execute(sql + ' ORDER BY RANDOM() LIMIT 1', params)
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def submit_review(image_id: int, user_id: str, status: str):
    """提交审核结果"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT OR REPLACE INTO reviews (image_id, user_id, status, reviewed_at) VALUES (?, ?, ?, ?)",
        (image_id, user_id, status, datetime.now().isoformat())
    )
    conn.commit()

    # 批量查询：一次性获取该用户参与的所有图片的全部投票
    # 注意：每次投票都重新检查所有历史图片以确保准确性（其他用户的后续投票
    # 可能改变之前的共识），这是一种权衡——用更多计算换取可信度实时精确。
    # 若用户投票历史极大（数万条），可考虑限制到最近 N 张图片或增量缓存。
    cursor.execute('''
        SELECT r.image_id, r.user_id, r.status, COALESCE(u.credibility_score, 0.5)
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.image_id IN (
            SELECT DISTINCT r2.image_id
            FROM reviews r2
            WHERE r2.user_id = ? AND r2.status IN ('pass', 'fail')
        )
        AND r.status IN ('pass', 'fail')
        ORDER BY r.image_id
    ''', (user_id,))
    all_rows = cursor.fetchall()
    
    # 按 image_id 分组为 dict[image_id] -> [(user_id, status, credibility)]
    groups: dict[int, list] = {}
    for row in all_rows:
        gid = row[0]
        if gid not in groups:
            groups[gid] = []
        groups[gid].append((row[1], row[2], row[3]))

    total = 0
    agrees = 0
    for gid, group in groups.items():
        # 只有 ≥2 人投票的图片才计入可信度（排除自证合理）
        result = compute_weighted_result(group, min_voters=2)
        if result is None:
            continue
        total += 1
        user_vote = next((r[1] for r in group if r[0] == user_id), None)
        if user_vote == result:
            agrees += 1

    if total > 0:
        new_score = (agrees + 1) / (total + 2)
        cursor.execute(
            "UPDATE users SET credibility_agrees = ?, credibility_total = ?, credibility_score = ? WHERE id = ?",
            (agrees, total, new_score, user_id)
        )

    conn.commit()
    conn.close()


def get_user_credibility(user_id: str) -> dict:
    """获取单个用户可信度"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT credibility_score, credibility_agrees, credibility_total FROM users WHERE id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"score": row[0], "agrees": row[1] or 0, "total": row[2] or 0}
    return {"score": None, "agrees": 0, "total": 0}


def get_all_credibility() -> list:
    """获取所有用户可信度"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nickname, credibility_score, credibility_agrees, credibility_total, is_banned FROM users ORDER BY credibility_score DESC NULLS LAST"
    )
    users = []
    for row in cursor.fetchall():
        users.append({
            "user_id": row[0],
            "nickname": row[1],
            "score": row[2],
            "agrees": row[3] or 0,
            "total": row[4] or 0,
            "is_banned": row[5]
        })
    conn.close()
    return users


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
            SUM(vote_count) as total_reviews,
            SUM(pass_count) as pass_count,
            SUM(fail_count) as fail_count,
            SUM(skip_count) as skip_count,
            COUNT(DISTINCT CASE WHEN vote_count >= ? THEN image_id END) as completed_images,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND pass_count >= ? THEN image_id END) as completed_pass,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count >= ? THEN image_id END) as completed_fail
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
    ''', (REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP))
    
    stats = cursor.fetchone()
    conn.close()
    
    total_reviews = stats['total_reviews'] or 0
    completed_images = stats['completed_images'] or 0
    completed_pass = stats['completed_pass'] or 0
    completed_fail = stats['completed_fail'] or 0
    completed_disputed = 0
    progress_percent = (total_reviews / (total_images * REQUIRED_VOTES) * 100) if total_images > 0 else 0
    
    return StatsResponse(
        total_images=total_images,
        reviewed_images=stats['reviewed_images'] or 0,
        total_reviews=total_reviews,
        pass_count=stats['pass_count'] or 0,
        fail_count=stats['fail_count'] or 0,
        skip_count=stats['skip_count'] or 0,
        progress_percent=round(progress_percent, 2),
        completed_images=completed_images,
        disputed_count=0,
        total_votes=total_reviews
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
            SUM(vote_count) as total_reviews,
            SUM(pass_count) as pass_count,
            SUM(fail_count) as fail_count,
            SUM(skip_count) as skip_count,
            COUNT(DISTINCT CASE WHEN vote_count >= ? THEN image_id END) as completed_images,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND pass_count >= ? THEN image_id END) as completed_pass,
            COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count >= ? THEN image_id END) as completed_fail
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
    """, (REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP, role_id))
    
    stats = cursor.fetchone()
    conn.close()
    
    if total_images == 0:
        return None
    
    total_reviews = stats["total_reviews"] or 0
    completed_images = stats["completed_images"] or 0
    completed_pass = stats["completed_pass"] or 0
    completed_fail = stats["completed_fail"] or 0
    completed_disputed = 0
    progress_percent = (total_reviews / (total_images * REQUIRED_VOTES) * 100) if total_images > 0 else 0
    
    return StatsResponse(
        total_images=total_images,
        reviewed_images=stats["reviewed_images"] or 0,
        total_reviews=total_reviews,
        pass_count=stats["pass_count"] or 0,
        fail_count=stats["fail_count"] or 0,
        skip_count=stats["skip_count"] or 0,
        progress_percent=round(progress_percent, 2),
        completed_images=completed_images,
        disputed_count=0,
        total_votes=total_reviews
    )

def get_image_final_status(image_id: int) -> Optional[str]:
    """获取图片最终审核状态（可信度加权）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.user_id, r.status, u.credibility_score
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.image_id = ? AND r.status IN ('pass', 'fail')
    ''', (image_id,))
    rows = cursor.fetchall()
    conn.close()
    return compute_weighted_result(rows)





def get_image_final_statuses_batch(image_ids):
    """Batch get final status for multiple images (可信度加权)."""
    if not image_ids:
        return {}
    validated_ids = list(dict.fromkeys(int(i) for i in image_ids if str(i).isdigit()))
    if not validated_ids:
        return {}
    result = {}
    conn = get_db()
    try:
        cursor = conn.cursor()
        for img_id in validated_ids:
            cursor.execute('''
                SELECT r.user_id, r.status, u.credibility_score
                FROM reviews r
                JOIN users u ON r.user_id = u.id
                WHERE r.image_id = ? AND r.status IN ('pass', 'fail')
            ''', (img_id,))
            rows = cursor.fetchall()
            result[img_id] = compute_weighted_result(rows)
    finally:
        conn.close()
    return result

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
        "backup_retention_days": get_setting("backup_retention_days") or "7",
        "notice": get_setting("notice") or "",
        "notice_version": get_setting("notice_version") or "0"
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

def _is_path_safe(path: str) -> bool:
    """验证路径安全，防止路径遍历"""
    if not path:
        return False
    # 只检查路径遍历字符，其他路径格式均可接受
    if '..' in path:
        return False
    return True

def clear_thumbnail_cache_for_role(role_id: int):
    """清除指定角色的缩略图缓存"""
    from backend.main import THUMBNAIL_CACHE_DIR
    if not os.path.exists(THUMBNAIL_CACHE_DIR):
        return 0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM images WHERE role_id = ?", (role_id,))
    image_ids = [row['id'] for row in cursor.fetchall()]
    conn.close()

    deleted = 0
    for img_id in image_ids:
        cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{img_id}.jpg")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                deleted += 1
            except Exception:
                pass
    return deleted
