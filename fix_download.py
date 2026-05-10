import re

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\js\app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加 AbortController 变量
old_global = '''// ========== 全局状态 ==========
let currentUser = null;
let currentImage = null;
let currentImageId = null;  // 当前显示的图片ID，用于防止错误切换
let currentRoleId = null;
let historyStack = [];'''

new_global = '''// ========== 全局状态 ==========
let currentUser = null;
let currentImage = null;
let currentImageId = null;  // 当前显示的图片ID，用于防止错误切换
let currentRoleId = null;
let historyStack = [];

// 下载控制器，用于取消进行中的下载
let thumbnailAbortController = null;
let fullImageAbortController = null;'''

content = content.replace(old_global, new_global)

# 新的loadImage函数 - 使用AbortController真正停止下载
new_load_image = '''// ========== 加载待审核图片（渐进加载：缩略图->原图）==========
async function loadImage() {
    const loading = document.getElementById('loadingIndicator');
    const noImage = document.getElementById('noImageHint');
    const image = document.getElementById('reviewImage');
    const skeleton = document.getElementById('imageSkeleton');

    // 取消之前的下载
    if (thumbnailAbortController) {
        thumbnailAbortController.abort();
        thumbnailAbortController = null;
    }
    if (fullImageAbortController) {
        fullImageAbortController.abort();
        fullImageAbortController = null;
    }

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
            // 创建新的 AbortController
            thumbnailAbortController = new AbortController();
            const thumbnailSignal = thumbnailAbortController.signal;

            // 第一步：先加载缩略图（快速预览）
            const thumbnailUrl = '/api/image/' + thisImageId + '/thumbnail?t=' + Date.now();

            // 使用 fetch + blob 方式，可以取消请求
            try {
                const thumbResponse = await fetch(thumbnailUrl, { signal: thumbnailSignal });
                if (!thumbResponse.ok) throw new Error('缩略图加载失败');

                const thumbBlob = await thumbResponse.blob();
                
                // 检查图片ID是否匹配
                if (currentImageId !== thisImageId) {
                    return;
                }

                // 显示缩略图
                const thumbUrl = URL.createObjectURL(thumbBlob);
                image.src = thumbUrl;
                
                // 隐藏骨架屏
                if (skeleton) skeleton.style.display = 'none';
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');
                
                // 清理旧的 blob URL
                if (image._thumbUrl) {
                    URL.revokeObjectURL(image._thumbUrl);
                }
                image._thumbUrl = thumbUrl;

                // 预加载原图
                fullImageAbortController = new AbortController();
                const fullSignal = fullImageAbortController.signal;
                const fullUrl = '/api/image/' + thisImageId + '/download?t=' + Date.now();

                try {
                    const fullResponse = await fetch(fullUrl, { signal: fullSignal });
                    if (fullResponse.ok) {
                        const fullBlob = await fullResponse.blob();
                        
                        // 检查图片ID是否匹配
                        if (currentImageId !== thisImageId) {
                            return;
                        }

                        const fullUrl2 = URL.createObjectURL(fullBlob);
                        
                        // 渐变切换到原图
                        image.style.transition = 'opacity 0.3s ease';
                        image.style.opacity = '0';

                        setTimeout(() => {
                            // 再次检查
                            if (currentImageId !== thisImageId) {
                                return;
                            }
                            
                            // 清理旧的 blob URL
                            if (image._fullUrl) {
                                URL.revokeObjectURL(image._fullUrl);
                            }
                            
                            image.src = fullUrl2;
                            image._fullUrl = fullUrl2;
                            image.style.transition = 'opacity 0.3s ease';
                            image.style.opacity = '1';
                            updateImageShadow(image);
                        }, 300);
                    }
                } catch (e) {
                    if (e.name === 'AbortError') {
                        // 下载被取消，忽略
                    }
                }

                updateImageShadow(image);
            } catch (e) {
                if (e.name === 'AbortError') {
                    // 缩略图下载被取消
                } else {
                    console.error('加载图片失败:', e);
                }
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

# 新的prevImage函数 - 也使用AbortController
new_prev_image = '''// ========== 上一张（渐进加载）==========
async function prevImage() {
    if (historyStack.length === 0) {
        alert('没有上一张图片');
        return;
    }

    // 取消当前的下载
    if (thumbnailAbortController) {
        thumbnailAbortController.abort();
        thumbnailAbortController = null;
    }
    if (fullImageAbortController) {
        fullImageAbortController.abort();
        fullImageAbortController = null;
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
        
        thumbnailAbortController = new AbortController();
        const thumbnailSignal = thumbnailAbortController.signal;
        
        // 先加载缩略图
        const thumbnailUrl = '/api/image/' + thisImageId + '/thumbnail?t=' + Date.now();

        try {
            const thumbResponse = await fetch(thumbnailUrl, { signal: thumbnailSignal });
            if (!thumbResponse.ok) throw new Error('缩略图加载失败');
            
            const thumbBlob = await thumbResponse.blob();
            
            // 检查图片ID是否匹配
            if (currentImageId !== thisImageId) {
                return;
            }

            const thumbUrl = URL.createObjectURL(thumbBlob);
            image.src = thumbUrl;
            
            if (skeleton) skeleton.style.display = 'none';
            image.style.display = 'block';
            image.style.opacity = '1';
            image.classList.add('loaded');
            
            if (image._thumbUrl) {
                URL.revokeObjectURL(image._thumbUrl);
            }
            image._thumbUrl = thumbUrl;

            // 预加载原图
            fullImageAbortController = new AbortController();
            const fullSignal = fullImageAbortController.signal;
            const fullUrl = '/api/image/' + thisImageId + '/download?t=' + Date.now();

            try {
                const fullResponse = await fetch(fullUrl, { signal: fullSignal });
                if (fullResponse.ok) {
                    const fullBlob = await fullResponse.blob();
                    
                    if (currentImageId !== thisImageId) {
                        return;
                    }

                    const fullUrl2 = URL.createObjectURL(fullBlob);
                    
                    image.style.transition = 'opacity 0.3s ease';
                    image.style.opacity = '0';

                    setTimeout(() => {
                        if (currentImageId !== thisImageId) {
                            return;
                        }
                        
                        if (image._fullUrl) {
                            URL.revokeObjectURL(image._fullUrl);
                        }
                        
                        image.src = fullUrl2;
                        image._fullUrl = fullUrl2;
                        image.style.transition = 'opacity 0.3s ease';
                        image.style.opacity = '1';
                        updateImageShadow(image);
                    }, 300);
                }
            } catch (e) {
                if (e.name !== 'AbortError') {
                    console.error('原图加载失败:', e);
                }
            }

            updateImageShadow(image);
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('缩略图加载失败:', e);
            }
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

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\js\app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('使用AbortController停止下载修复完成')
