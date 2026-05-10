import re
import os

os.chdir(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review')

# 读取文件
with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 新的渐进加载的loadImage函数
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
            return;
        }

        currentImage = data.image;

        if (image) {
            // 第一步：先加载缩略图（快速预览）
            const thumbnailUrl = '/api/image/' + currentImage.id + '/thumbnail?t=' + Date.now();
            image.src = thumbnailUrl;

            // 缩略图加载完成：显示缩略图
            image.onload = function() {
                // 隐藏骨架屏
                if (skeleton) skeleton.style.display = 'none';
                // 显示缩略图（带渐入）
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');

                // 立即预加载原图
                const fullImage = new Image();
                const fullUrl = '/api/image/' + currentImage.id + '/download?t=' + Date.now();
                fullImage.onload = function() {
                    // 原图加载完成，渐变切换到原图
                    image.style.transition = 'opacity 0.3s ease';
                    image.style.opacity = '0';

                    setTimeout(() => {
                        image.src = fullUrl;
                        image.onload = function() {
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

                // 立即预加载原图
                const fullImage = new Image();
                fullImage.onload = function() {
                    image.style.transition = 'opacity 0.3s ease';
                    image.style.opacity = '0';
                    setTimeout(() => {
                        image.src = image.src;
                        image.style.opacity = '1';
                    }, 300);
                };
                const fullUrl = '/api/image/' + currentImage.id + '/download?t=' + Date.now();
                fullImage.src = fullUrl;

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

# 新的prevImage函数
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
        // 先加载缩略图
        const thumbnailUrl = '/api/image/' + currentImage.id + '/thumbnail?t=' + Date.now();
        image.src = thumbnailUrl;

        image.onload = function() {
            if (skeleton) skeleton.style.display = 'none';
            image.style.display = 'block';
            image.style.opacity = '1';
            image.classList.add('loaded');

            // 预加载原图
            const fullImage = new Image();
            const fullUrl = '/api/image/' + currentImage.id + '/download?t=' + Date.now();
            fullImage.onload = function() {
                image.style.transition = 'opacity 0.3s ease';
                image.style.opacity = '0';
                setTimeout(() => {
                    image.src = fullUrl;
                    image.onload = function() {
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

# 替换loadImage函数 - 找到函数开始和结束
loadImage_start = content.find('// ========== 加载待审核图片 ==========')
if loadImage_start == -1:
    print('找不到loadImage函数')
    exit(1)

# 找到下一个函数的开始
next_func_start = content.find('// ==========', loadImage_start + 50)
if next_func_start == -1:
    print('找不到下一个函数')
    exit(1)

# 替换loadImage
content = content[:loadImage_start] + new_load_image + content[next_func_start:]

# 现在处理prevImage
prev_start = content.find('// ========== 上一张 ==========')
if prev_start == -1:
    print('找不到prevImage函数')
    exit(1)

next_func2_start = content.find('// ==========', prev_start + 50)
if next_func2_start == -1:
    next_func2_start = len(content)

# 替换prevImage
content = content[:prev_start] + new_prev_image + content[next_func2_start:]

# 写回文件
with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('渐进加载已实现成功')