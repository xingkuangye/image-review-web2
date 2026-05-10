import re

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\js\app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 添加 currentImageId 变量
old_global = '''// ========== 全局状态 ==========
let currentUser = null;
let currentImage = null;
let currentRoleId = null;
let historyStack = [];'''

new_global = '''// ========== 全局状态 ==========
let currentUser = null;
let currentImage = null;
let currentImageId = null;  // 当前显示的图片ID，用于防止错误切换
let currentRoleId = null;
let historyStack = [];'''

content = content.replace(old_global, new_global)

# 2. 新的loadImage函数 - 带防误切换逻辑
new_load_image = '''// ========== 加载待审核图片（渐进加载：缩略图->原图）==========
async function loadImage() {
    const loading = document.getElementById('loadingIndicator');
    const noImage = document.getElementById('noImageHint');
    const image = document.getElementById('reviewImage');
    const skeleton = document.getElementById('imageSkeleton');

    // 显示骨架屏
    if (skeleton) skeleton.style.display = 'flex';
    if (loading) loading.style.display = 'none';
    if (noImage) noImage.style.display = 'none';
    if (image) {
        image.style.display = 'none';
        image.classList.remove('loaded');
        image.style.opacity = '0';
    }

    // 确保用户已初始化
    if (!currentUser || !currentUser.id) {
        if (skeleton) skeleton.textContent = '等待初始化...';
        setTimeout(loadImage, 500);
        return;
    }

    try {
        const userId = currentUser.id;
        const url = currentRoleId
            ? `/api/image/review?user_id=${userId}&role_id=${currentRoleId}`
            : `/api/image/review?user_id=${userId}`;

        const response = await fetch(url);
        const data = await response.json();

        if (!data.image) {
            if (skeleton) skeleton.style.display = 'none';
            if (noImage) noImage.style.display = 'block';
            currentImage = null;
            currentImageId = null;
            return;
        }

        currentImage = data.image;
        const thisImageId = currentImage.id;  // 保存本次加载的图片ID
        currentImageId = thisImageId;  // 更新全局当前图片ID

        if (image) {
            // 第一步：先加载缩略图（快速预览）
            const thumbnailUrl = '/api/image/' + thisImageId + '/thumbnail?t=' + Date.now();
            image.src = thumbnailUrl;

            // 缩略图加载完成：显示缩略图
            image.onload = function() {
                // 检查图片ID是否匹配，防止切换到已审核的图片
                if (currentImageId !== thisImageId) {
                    return;
                }
                
                // 隐藏骨架屏
                if (skeleton) skeleton.style.display = 'none';
                // 显示缩略图（带渐入）
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');

                // 立即预加载原图
                const fullImage = new Image();
                const fullUrl = '/api/image/' + thisImageId + '/download?t=' + Date.now();
                fullImage.onload = function() {
                    // 检查图片ID是否匹配，防止错误切换
                    if (currentImageId !== thisImageId) {
                        return;
                    }
                    
                    // 原图加载完成，渐变切换到原图
                    image.style.transition = 'opacity 0.3s ease';
                    image.style.opacity = '0';

                    setTimeout(() => {
                        // 再次检查，因为可能在setTimeout期间用户切换了图片
                        if (currentImageId !== thisImageId) {
                            return;
                        }
                        image.src = fullUrl;
                        image.onload = function() {
                            if (currentImageId !== thisImageId) {
                                return;
                            }
                            image.style.transition = 'opacity 0.3s ease';
                            image.style.opacity = '1';
                            updateImageShadow(this);
                        };
                        // 如果原图已经在缓存中
                        if (image.complete) {
                            image.style.opacity = '1';
                            updateImageShadow(image);
                        }
                    }, 300);
                };
                fullImage.src = fullUrl;

                // 尝试提取颜色更新阴影
                updateImageShadow(this);
            };

            // 如果缩略图已经在缓存中
            if (image.complete) {
                if (skeleton) skeleton.style.display = 'none';
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');
                updateImageShadow(image);
            }
        }

        // 更新角色进度
        if (currentRoleId) {
            await loadRoleProgress();
        }

    } catch (e) {
        if (skeleton) skeleton.style.display = 'none';
        console.error('加载图片失败:', e);
    }
}'''

# 找到并替换loadImage函数
loadImage_start = content.find('// ========== 加载待审核图片（渐进加载：缩略图->原图）==========')
if loadImage_start != -1:
    next_func = content.find('// ==========', loadImage_start + 50)
    if next_func == -1:
        next_func = len(content)
    content = content[:loadImage_start] + new_load_image + content[next_func:]

# 3. 修改prevImage函数 - 更新currentImageId
new_prev_image = '''// ========== 上一张（渐进加载）==========
async function prevImage() {
    if (historyStack.length === 0) {
        alert('没有上一张图片');
        return;
    }

    // 如果当前有图片且未审核，先审核为跳过
    if (currentImage && currentUser) {
        const userStatus = currentImage.is_reviewed_by_user;
        if (!userStatus) {
            await fetch(`/api/image/${currentImage.id}/review`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `user_id=${currentUser.id}&status=skip`
            });
        }
    }

    currentImage = historyStack.pop();
    currentImageId = currentImage.id;  // 更新当前图片ID

    const image = document.getElementById('reviewImage');
    const loading = document.getElementById('loadingIndicator');
    const noImage = document.getElementById('noImageHint');
    const skeleton = document.getElementById('imageSkeleton');

    // 显示骨架屏
    if (skeleton) skeleton.style.display = 'flex';
    if (loading) loading.style.display = 'none';
    if (noImage) noImage.style.display = 'none';
    if (image) {
        image.style.display = 'none';
        image.classList.remove('loaded');
        image.style.opacity = '0';
    }

    if (image) {
        const thisImageId = currentImage.id;
        // 先加载缩略图
        const thumbnailUrl = '/api/image/' + thisImageId + '/thumbnail?t=' + Date.now();
        image.src = thumbnailUrl;

        image.onload = function() {
            // 检查图片ID是否匹配
            if (currentImageId !== thisImageId) {
                return;
            }
            
            if (skeleton) skeleton.style.display = 'none';
            image.style.display = 'block';
            image.style.opacity = '1';
            image.classList.add('loaded');

            // 预加载原图
            const fullImage = new Image();
            const fullUrl = '/api/image/' + thisImageId + '/download?t=' + Date.now();
            fullImage.onload = function() {
                if (currentImageId !== thisImageId) {
                    return;
                }
                
                image.style.transition = 'opacity 0.3s ease';
                image.style.opacity = '0';
                setTimeout(() => {
                    if (currentImageId !== thisImageId) {
                        return;
                    }
                    image.src = fullUrl;
                    image.onload = function() {
                        if (currentImageId !== thisImageId) {
                            return;
                        }
                        image.style.transition = 'opacity 0.3s ease';
                        image.style.opacity = '1';
                        updateImageShadow(this);
                    };
                    if (image.complete) {
                        image.style.opacity = '1';
                        updateImageShadow(image);
                    }
                }, 300);
            };
            fullImage.src = fullUrl;

            updateImageShadow(this);
        };

        if (image.complete) {
            if (skeleton) skeleton.style.display = 'none';
            image.style.display = 'block';
            image.style.opacity = '1';
            image.classList.add('loaded');
            updateImageShadow(image);
        }
    }
}'''

# 找到并替换prevImage函数
prev_start = content.find('// ========== 上一张（渐进加载）==========')
if prev_start != -1:
    next_func2 = content.find('// ==========', prev_start + 50)
    if next_func2 == -1:
        next_func2 = len(content)
    content = content[:prev_start] + new_prev_image + content[next_func2:]
else:
    # 找不到新函数，尝试找旧的prevImage
    prev_start = content.find('// ========== 上一张 ==========')
    if prev_start != -1:
        next_func2 = content.find('// ==========', prev_start + 50)
        if next_func2 == -1:
            next_func2 = len(content)
        content = content[:prev_start] + new_prev_image + content[next_func2:]

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\js\app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('渐进加载防误切换修复完成')
