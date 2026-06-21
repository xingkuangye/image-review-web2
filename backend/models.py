from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# 用户相关
class UserCreate(BaseModel):
    nickname: Optional[str] = "匿名用户"

class UserUpdate(BaseModel):
    nickname: str

class UserResponse(BaseModel):
    id: str
    nickname: str
    created_at: str
    last_active: str
    is_banned: int
    total_reviews: int = 0
    user_token: Optional[str] = None

# 角色相关
class RoleCreate(BaseModel):
    name: str
    image_path: str

class RoleResponse(BaseModel):
    id: int
    name: str
    image_path: str
    avatar_path: Optional[str]
    total_images: int = 0
    reviewed_images: int = 0
    pass_count: int = 0
    fail_count: int = 0

# 图片相关
class ImageResponse(BaseModel):
    id: int
    path: str
    role_id: Optional[int]
    role_name: Optional[str] = None
    review_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    is_reviewed_by_user: Optional[str] = None

# 审核相关
class ReviewCreate(BaseModel):
    image_id: int
    status: str  # "pass", "fail", "skip"

# 统计相关
class StatsResponse(BaseModel):
    total_images: int
    reviewed_images: int
    total_reviews: int
    pass_count: int
    fail_count: int
    skip_count: int
    progress_percent: float
    completed_images: int = 0  # 完成审核的图片数（5人投票且≥3通过）
    disputed_count: int = 0  # 有争议的图片数（审核完毕但未通过/未不通过）
    total_votes: int = 0  # 总投票数

class RoleStatsResponse(BaseModel):
    role: RoleResponse
    stats: StatsResponse
