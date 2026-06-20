// ========== 全局状态 ==========
let currentUser = null;
let currentImage = null;
let currentImageId = null;  // 当前显示的图片ID，用于防止错误切换
let currentRoleId = null;
let historyStack = [];

// 下载控制器，用于取消进行中的下载
let thumbnailAbortController = null;
let fullImageAbortController = null;

// 预加载下一张图片
let preloadNextId = null;
let preloadBlobUrl = null;

// ========== 图片阴影管理器 ==========
class ImageShadowManager {
    constructor(options = {}) {
        // 配置项
        this.config = {
            sampleSize: options.sampleSize || 50,           // 采样区域大小
            minBrightness: options.minBrightness || 20,      // 最小亮度阈值（排除纯黑）
            maxBrightness: options.maxBrightness || 235,     // 最大亮度阈值（排除纯白）
            shadowIntensity: options.shadowIntensity || 0.3,  // 阴影强度（0~1）
            shadowOpacity: options.shadowOpacity || 0.6,     // 阴影透明度
            baseBlur: options.baseBlur || 32,                // 基础模糊半径
            baseOffset: options.baseOffset || 8,            // 基础偏移量
            referenceSize: options.referenceSize || 800,     // 参考尺寸
            minScale: options.minScale || 0.5,               // 最小缩放
            maxScale: options.maxScale || 2.0,               // 最大缩放
            transitionDuration: options.transitionDuration || 300  // 过渡动画时长(ms)
        };
        
        // 缓存
        this.cache = new Map();
        this.cacheMaxSize = 20;
        
        // 超时管理
        this.debounceTimer = null;
        this.debounceDelay = 100;
        
        // 获取容器元素
        this.container = null;
    }
    
    /**
     * 获取图片容器元素
     */
    getContainer() {
        if (!this.container) {
            this.container = document.querySelector('.image-container');
        }
        return this.container;
    }
    
    /**
     * 更新容器引用
     */
    refreshContainer() {
        this.container = null;
        return this.getContainer();
    }
    
    /**
     * 计算图片平均颜色
     */
    calculateAverageColor(imageElement) {
        if (!imageElement || !imageElement.complete) return null;
        
        try {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const { sampleSize } = this.config;
            
            canvas.width = sampleSize;
            canvas.height = sampleSize;
            
            // 绘制缩小后的图片
            ctx.drawImage(imageElement, 0, 0, sampleSize, sampleSize);
            
            // 获取像素数据
            const imageData = ctx.getImageData(0, 0, sampleSize, sampleSize);
            const data = imageData.data;
            
            let r = 0, g = 0, b = 0, count = 0;
            
            // 遍历像素，计算平均值（排除过亮和过暗的像素）
            const { minBrightness, maxBrightness } = this.config;
            
            for (let i = 0; i < data.length; i += 4) {
                const red = data[i];
                const green = data[i + 1];
                const blue = data[i + 2];
                const brightness = (red + green + blue) / 3;
                
                // 跳过极暗或极亮的像素
                if (brightness < minBrightness || brightness > maxBrightness) continue;
                
                r += red;
                g += green;
                b += blue;
                count++;
            }
            
            if (count === 0) return null;
            
            return {
                r: Math.round(r / count),
                g: Math.round(g / count),
                b: Math.round(b / count),
                count: count
            };
        } catch (e) {
            console.warn('颜色采样失败:', e);
            return null;
        }
    }
    
    /**
     * 计算阴影尺寸参数
     */
    calculateShadowScale(imageWidth, imageHeight) {
        const { referenceSize, minScale, maxScale } = this.config;
        const maxDim = Math.max(imageWidth, imageHeight);
        
        // 根据图片尺寸计算缩放因子
        const scaleFactor = Math.min(Math.max(maxDim / referenceSize, minScale), maxScale);
        
        return {
            scaleFactor: scaleFactor,
            blurRadius: Math.round(this.config.baseBlur * scaleFactor),
            offsetY: Math.round(this.config.baseOffset * scaleFactor)
        };
    }
    
    /**
     * 生成阴影 CSS 值
     */
    generateShadowStyle(colorData, scaleData) {
        const { shadowIntensity, shadowOpacity } = this.config;
        
        // 计算阴影颜色（降低亮度）
        const shadowR = Math.round(colorData.r * shadowIntensity);
        const shadowG = Math.round(colorData.g * shadowIntensity);
        const shadowB = Math.round(colorData.b * shadowIntensity);
        
        // 生成多层阴影
        const { blurRadius, offsetY } = scaleData;
        
        // 主阴影
        const mainShadow = `0 ${offsetY}px ${blurRadius}px rgba(${shadowR}, ${shadowG}, ${shadowB}, ${shadowOpacity})`;
        // 内层阴影
        const innerShadow = `0 ${Math.round(offsetY / 2)}px ${Math.round(blurRadius / 2)}px rgba(0, 0, 0, ${shadowOpacity * 0.7})`;
        
        return `${mainShadow}, ${innerShadow}`;
    }
    
    /**
     * 验证图片是否需要更新（使用缓存）
     */
    shouldUpdate(imageId, width, height, colorHash) {
        const key = `${imageId}-${width}x${height}`;
        const cached = this.cache.get(key);
        
        if (cached && cached.colorHash === colorHash) {
            return { shouldUpdate: false, cachedStyle: cached.style };
        }
        
        return { shouldUpdate: true, key: key };
    }
    
    /**
     * 生成颜色哈希（用于缓存验证）
     */
    generateColorHash(r, g, b) {
        return `${r}-${g}-${b}`;
    }
    
    /**
     * 更新阴影（主入口）
     */
    update(imageElement, imageId = null) {
        // 参数验证
        if (!imageElement || !imageElement.complete || !imageElement.naturalWidth) {
            return false;
        }
        
        // 防抖处理
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this._doUpdate(imageElement, imageId);
        }, this.debounceDelay);
        
        return true;
    }
    
    /**
     * 实际执行更新
     */
    _doUpdate(imageElement, imageId) {
        // 计算颜色
        const colorData = this.calculateAverageColor(imageElement);
        if (!colorData) {
            this.clearShadow();
            return;
        }
        
        // 计算尺寸参数
        const scaleData = this.calculateShadowScale(
            imageElement.naturalWidth,
            imageElement.naturalHeight
        );
        
        // 生成阴影样式
        const shadowStyle = this.generateShadowStyle(colorData, scaleData);
        
        // 应用到容器
        const container = this.getContainer();
        if (container) {
            container.style.boxShadow = shadowStyle;
        }
        
        // 更新缓存
        if (imageId) {
            const key = `${imageId}-${imageElement.naturalWidth}x${imageElement.naturalHeight}`;
            const colorHash = this.generateColorHash(colorData.r, colorData.g, colorData.b);
            
            // 清理旧缓存
            if (this.cache.size >= this.cacheMaxSize) {
                const firstKey = this.cache.keys().next().value;
                this.cache.delete(firstKey);
            }
            
            this.cache.set(key, { style: shadowStyle, colorHash: colorHash });
        }
    }
    
    /**
     * 清除阴影
     */
    clearShadow() {
        const container = this.getContainer();
        if (container) {
            container.style.boxShadow = '';
        }
    }
    
    /**
     * 设置过渡动画
     */
    enableTransition() {
        const container = this.getContainer();
        if (container) {
            container.style.transition = `box-shadow ${this.config.transitionDuration}ms ease-out`;
        }
    }
    
    /**
     * 禁用过渡动画
     */
    disableTransition() {
        const container = this.getContainer();
        if (container) {
            container.style.transition = 'none';
        }
    }
    
    /**
     * 批量更新配置
     */
    setConfig(options) {
        Object.assign(this.config, options);
    }
    
    /**
     * 获取当前配置
     */
    getConfig() {
        return { ...this.config };
    }
    
    /**
     * 清除缓存
     */
    clearCache() {
        this.cache.clear();
    }
}

// 创建阴影管理器实例
const imageShadowManager = new ImageShadowManager();

// 兼容旧接口的函数
function updateImageShadow(imageElement) {
    return imageShadowManager.update(imageElement);
}

// ========== 初始化 ==========
window.addEventListener('DOMContentLoaded', async function() {
    try {
        // 初始化阴影管理器
        imageShadowManager.enableTransition();
        
        await loadSettings();  // 先加载配置
        await checkNotice();
        await initUser();
        await loadStats();
        await loadImage();
    } catch (e) {
        console.error('初始化失败:', e);
    }
});

// ========== 用户初始化 ==========
async function initUser() {
    try {
        // 尝试从localStorage获取用户ID
        let userId = localStorage.getItem('review_user_id');
        
        let response;
        if (!userId) {
            // 创建新用户
            response = await fetch('/api/user/init');
            if (!response.ok) throw new Error('创建用户失败');
            currentUser = await response.json();
            localStorage.setItem('review_user_id', currentUser.id);
        } else {
            // 获取现有用户
            response = await fetch(`/api/user/${userId}`);
            if (!response.ok) {
                localStorage.removeItem('review_user_id');
                await initUser();
                return;
            }
            currentUser = await response.json();
        }
        
        updateUserUI();
    } catch (e) {
        console.error('初始化用户失败:', e);
    }
}

function updateUserUI() {
    document.getElementById('userNickname').textContent = currentUser.nickname;
    document.getElementById('userReviewCount').textContent = currentUser.total_reviews;
}

// ========== 加载统计数据 ==========
async function loadStats() {
    try {
        const [statsRes, userRes] = await Promise.all([
            fetch('/api/stats'),
            currentUser ? fetch(`/api/user-stats?user_id=${currentUser.id}`) : Promise.resolve(null)
        ]);
        if (!statsRes.ok) throw new Error('API请求失败');
        const stats = await statsRes.json();
        const userStats = userRes ? await userRes.json() : null;
        
        const progressPercent = document.getElementById('progressPercent');
        const progressFill = document.getElementById('progressFill');
        const reviewedCount = document.getElementById('reviewedCount');
        const totalCount = document.getElementById('totalCount');
        const userReviewCount = document.getElementById('userReviewCount');
        const completeCount = document.getElementById('completeCount');
        const totalImages = document.getElementById('totalImages');
        
        if (progressPercent) progressPercent.textContent = (stats.progress_percent || 0).toFixed(1);
        if (progressFill) progressFill.style.width = (stats.progress_percent || 0) + '%';
        if (reviewedCount) reviewedCount.textContent = stats.total_reviews || 0;
        // 投票进度条显示总票数 = 图片数 × 每张图片需要的票数
        if (totalCount) totalCount.textContent = (stats.total_images || 0) * appConfig.required_votes;
        
        // 更新完成审核数
        if (completeCount) completeCount.textContent = stats.completed_images || 0;
        if (totalImages) totalImages.textContent = stats.total_images || 0;
        
        // Update top progress bar
        const topFill = document.getElementById('topProgressFill');
        if (topFill) {
            topFill.style.width = (stats.progress_percent || 0) + '%';
        }
        
        // 更新用户审核数（当前用户自己的审核数）
        if (currentUser && userStats) {
            currentUser.total_reviews = userStats.total_reviews || 0;
            if (userReviewCount) userReviewCount.textContent = currentUser.total_reviews;
        }
    } catch (e) {
        console.error('加载统计数据失败:', e);
    }
}


// ========== 加载进度条控制 ==========
function showLoadingBar(text) {
    var el = document.getElementById('loadingIndicator2');
    if (el) el.style.display = 'flex';
    var txt = document.getElementById('loadingText');
    if (txt) txt.textContent = text || '';
    var badge = document.getElementById('roleBadge');
    if (badge) badge.style.display = 'none';
}
function hideLoadingBar() {
    var el = document.getElementById('loadingIndicator2');
    if (el) el.style.display = 'none';
    updateRoleBadge();
}
function setLoadingLabel(text) {
    var txt = document.getElementById('loadingText');
    if (txt) txt.textContent = text || '';
}



// ========== 加载待审核图片（渐进加载：缩略图->原图）==========
async function loadImage() {
    var noImage = document.getElementById('noImageHint');
    const image = document.getElementById('reviewImage');

    // 取消之前的下载
    if (thumbnailAbortController) {
        thumbnailAbortController.abort();
        thumbnailAbortController = null;
    }
    if (fullImageAbortController) {
        fullImageAbortController.abort();
        fullImageAbortController = null;
    }

    // 显示加载中转圈
    showLoadingBar('加载图片...')
    if (noImage) noImage.style.display = 'none';
    if (image) {
        image.style.display = 'none';
        image.classList.remove('loaded');
        image.style.opacity = '0';
    }

    // 确保用户已初始化
    if (!currentUser || !currentUser.id) {
        setLoadingLabel('等待初始化...')
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
            hideLoadingBar()
            if (noImage) noImage.style.display = 'block';
            currentImage = null;
            currentImageId = null;
            updateRoleBadge();
            return;
        }

        currentImage = data.image;
        preloadNextId = (data.next_image_id !== data.image?.id && data.next_image_id) || null;
        updateRoleBadge();
        const thisImageId = currentImage.id;  // 保存本次加载的图片ID
        currentImageId = thisImageId;  // 更新全局当前图片ID

        if (image) {
            // 创建新的 AbortController
            thumbnailAbortController = new AbortController();
            const thumbnailSignal = thumbnailAbortController.signal;

            // 第一步：先加载缩略图（快速预览）
            // 检查预加载缓存
            if (preloadBlobUrl && preloadNextId === thisImageId) {
                image.src = preloadBlobUrl;
                preloadBlobUrl = null;
                preloadNextId = null;
                hideLoadingBar()
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');
                image.classList.add('enter');
                setTimeout(function() { image.classList.remove('enter'); }, 300);
                
                // 后台加载原图
                fullImageAbortController = new AbortController();
                var fullSignal = fullImageAbortController.signal;
                var fullUrl = '/api/image/' + thisImageId + '/download?t=' + Date.now();
                fetch(fullUrl, { signal: fullSignal }).then(function(r) { return r.blob(); }).then(function(blob) {
                    if (currentImageId !== thisImageId) return;
                    var url2 = URL.createObjectURL(blob);
                    if (image._fullUrl) URL.revokeObjectURL(image._fullUrl);
                    image.src = url2;
                    image._fullUrl = url2;
                    updateImageShadow(image);
                }).catch(function(e) { if (e.name !== 'AbortError') console.error('原图加载失败:', e); });
                return;
            }
            
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
                hideLoadingBar()
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');
                image.classList.add('enter');
                setTimeout(function() { image.classList.remove('enter'); }, 300);
                
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
                        
                        // 直接替换图片，无需动画
                        if (currentImageId !== thisImageId) {
                            return;
                        }
                        
                        // 清理旧的 blob URL
                        if (image._fullUrl) {
                            URL.revokeObjectURL(image._fullUrl);
                        }
                        
                        image.src = fullUrl2;
                        image._fullUrl = fullUrl2;
                        updateImageShadow(image);
                    }
                } catch (e) {
                    if (e.name === 'AbortError') {
                        // 下载被取消，忽略
                    }
                }

                updateImageShadow(image);
                // 预加载下一张缩略图
                preloadNextThumbnail();
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
        hideLoadingBar()
        console.error('加载图片失败:', e);
    }
}// ========== 加载角色进度 ==========
async function loadRoleProgress() {
    try {
        const response = await fetch('/api/roles');
        const roles = await response.json();
        const role = roles.find(r => r.id === currentRoleId);
        
        if (role) {
            const percent = role.total_images > 0 
                ? ((role.reviewed_images || 0) / role.total_images * 100).toFixed(1)
                : 0;
            
            document.getElementById('roleProgress').style.display = 'inline';
            document.getElementById('roleProgressPercent').textContent = percent;
        }
    } catch (e) {
        console.error('加载角色进度失败:', e);
    }
}


// ========== 按钮视觉反馈 ==========
// ========== 指针位置跟踪（用于涟漪） ==========
document.addEventListener('pointerdown', function(e) {
    window._lastPointerX = e.clientX;
    window._lastPointerY = e.clientY;
});

// ========== 按钮视觉反馈（涟漪） ==========
function flashButton(btnId) {
    var btn = document.getElementById(btnId);
    if (btn && btn.offsetParent === null) { btn = null; }
    if (!btn) {
        var map = { passBtn: '.nav-pass', failBtn: '.nav-fail', prevBtn: '.nav-prev', downloadBtn: '.nav-download', skipBtn: '.nav-prev' };
        btn = document.querySelector('.mobile-bottom-nav ' + (map[btnId] || ''));
    }
    if (!btn) return;
    createRipple(btn);
}

function createRipple(btn) {
    var old = document.querySelector('.ripple');
    if (old) old.remove();
    var rect = btn.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height) * 1.5;
    var cx = window._lastPointerX !== undefined ? window._lastPointerX : rect.left + rect.width / 2;
    var cy = window._lastPointerY !== undefined ? window._lastPointerY : rect.top + rect.height / 2;
    var span = document.createElement('span');
    span.className = 'ripple';
    span.style.width = span.style.height = size + 'px';
    span.style.left = (cx - size / 2) + 'px';
    span.style.top = (cy - size / 2) + 'px';
    if (btn.classList.contains('btn-pass') || btn.classList.contains('nav-pass')) {
        span.style.background = 'rgba(74, 222, 128, 0.2)';
    } else if (btn.classList.contains('btn-fail') || btn.classList.contains('nav-fail')) {
        span.style.background = 'rgba(248, 113, 113, 0.2)';
    } else if (btn.classList.contains('btn-download') || btn.classList.contains('nav-download')) {
        span.style.background = 'rgba(91, 141, 239, 0.2)';
    } else if (btn.classList.contains('btn-prev') || btn.classList.contains('nav-prev') || btn.classList.contains('btn-skip')) {
        span.style.background = 'rgba(255, 255, 255, 0.1)';
    }
    document.body.appendChild(span);
    setTimeout(function() { span.remove(); }, 500);
}


// ========== 预加载下一张缩略图 ==========
function preloadNextThumbnail() {
    if (!preloadNextId) return;
    
    // 清理旧预加载
    if (preloadBlobUrl) {
        URL.revokeObjectURL(preloadBlobUrl);
        preloadBlobUrl = null;
    }
    
    var imgId = preloadNextId;
    var url = '/api/image/' + imgId + '/thumbnail?t=' + Date.now();
    
    fetch(url)
        .then(function(r) { return r.blob(); })
        .then(function(blob) {
            preloadBlobUrl = URL.createObjectURL(blob);
        })
        .catch(function() {});
}

// ========== 提交审核 ==========
// 全局审核锁定：骨架屏显示时拒绝审核
var reviewLocked = false;
var reviewLockTimer = null;

async function submitReview(status) {
    if (!currentImage || !currentUser) return;
    if (reviewLocked) return;
    reviewLocked = true;
    // 安全兜底：10秒后强制解锁
    if (reviewLockTimer) clearTimeout(reviewLockTimer);
    reviewLockTimer = setTimeout(function() { reviewLocked = false; reviewLockTimer = null; }, 10000);
    flashButton(status === 'pass' ? 'passBtn' : status === 'fail' ? 'failBtn' : '');
    
    // 1. 旧图片 + 角色名消失
    var image = document.getElementById('reviewImage');
    var noImage = document.getElementById('noImageHint');
    if (image) {
        image.style.display = 'none';
        image.classList.remove('loaded');
        image.classList.remove('enter');
    }
    if (noImage) noImage.style.display = 'none';
    var badge = document.getElementById('roleBadge');
    if (badge) badge.style.display = 'none';
    
    // 2. 丢弃正在进行的下载请求
    if (thumbnailAbortController) { thumbnailAbortController.abort(); thumbnailAbortController = null; }
    if (fullImageAbortController) { fullImageAbortController.abort(); fullImageAbortController = null; }
    
    // 3. 显示加载中转圈
    showLoadingBar('提交审核结果...');
    
    try {
        // 4. 同步审核状态到服务器
        setLoadingLabel('上传审核结果中...');
        await fetch(`/api/image/${currentImage.id}/review`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `user_id=${currentUser.id}&status=${status}`
        });
        
        // 保存到历史
        historyStack.push(currentImage);
        
        // 同步统计
        await loadStats();
        
        // 5. 加载新图片
        setLoadingLabel('获取新图片...');
        if (preloadBlobUrl && preloadNextId && preloadNextId !== currentImage?.id) {
            // 使用预加载缓存
            var nextId = preloadNextId;
            var blobUrl = preloadBlobUrl;
            preloadNextId = null;
            preloadBlobUrl = null;
            
            currentImage = { id: nextId, role_name: '' };
            currentImageId = nextId;
            
            // 6. 先更新文案再延迟隐藏，让用户看到状态变化
            setLoadingLabel('加载图片信息...');
            // 稍微延迟隐藏转圈，让文案可见
            setTimeout(function() { hideLoadingBar(); }, 120);
            if (image) {
                image.src = blobUrl;
                image.style.display = 'block';
                image.style.opacity = '1';
                image.classList.add('loaded');
                image.classList.add('enter');
                setTimeout(function() { image.classList.remove('enter'); }, 300);
                if (image._thumbUrl) URL.revokeObjectURL(image._thumbUrl);
                image._thumbUrl = blobUrl;
            }
            
            // 7. 解锁审核
            reviewLocked = false;
            
            // 8. 获取当前图片的角色名 + 预加载下一张
            var uid = currentUser.id;
            var roleParam = currentRoleId ? '&role_id=' + currentRoleId : '';
            
            // 预加载下一张
            var nextUrl = '/api/image/next-id?user_id=' + uid + '&current_id=' + nextId + roleParam;
            fetch(nextUrl).then(function(r) { return r.json(); }).then(function(d) {
                // 更新当前图片角色名
                if (d.role_name && currentImage && currentImage.id === nextId) {
                    currentImage.role_name = d.role_name;
                    updateRoleBadge();
                }
                if (d.next_image_id) {
                    preloadNextId = d.next_image_id;
                    fetch('/api/image/' + d.next_image_id + '/thumbnail?t=' + Date.now())
                        .then(function(r) { return r.blob(); })
                        .then(function(blob) { preloadBlobUrl = URL.createObjectURL(blob); })
                        .catch(function() {});
                }
            }).catch(function() {});
            

            
            // 9. 开始获取原图（后台）
            var fullSig = new AbortController();
            fullImageAbortController = fullSig;
            fetch('/api/image/' + nextId + '/download?t=' + Date.now(), { signal: fullSig.signal })
                .then(function(r) { return r.blob(); })
                .then(function(blob) {
                    if (currentImageId !== nextId) return;
                    var fUrl = URL.createObjectURL(blob);
                    if (image._fullUrl) URL.revokeObjectURL(image._fullUrl);
                    image.src = fUrl;
                    image._fullUrl = fUrl;
                    updateImageShadow(image);
                }).catch(function(e) { if (e.name !== 'AbortError') console.error('原图加载失败:', e); });
            
            return;
        }
        
        // fallback: 没有预加载缓存时正常调 API
        await loadImage();
        reviewLocked = false;
        hideLoadingBar();
        
    } catch (e) {
        reviewLocked = false;
        hideLoadingBar();
        console.error('提交审核失败:', e);
        alert('提交失败，请重试');
    }
}

// ========== 上一张（渐进加载）==========
async function prevImage() {
    flashButton('prevBtn');
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
    updateRoleBadge();
    preloadNextId = null;
    if (preloadBlobUrl) { URL.revokeObjectURL(preloadBlobUrl); preloadBlobUrl = null; }
    const image = document.getElementById('reviewImage');
    var noImage = document.getElementById('noImageHint');

    // 显示骨架屏
    showLoadingBar('加载图片...')
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
            
            hideLoadingBar()
            image.style.display = 'block';
            image.style.opacity = '1';
            image.classList.add('loaded');
            image.classList.add('enter');
            setTimeout(function() { image.classList.remove('enter'); }, 300);
            
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
                    
                    if (currentImageId !== thisImageId) {
                        return;
                    }
                    
                    if (image._fullUrl) {
                        URL.revokeObjectURL(image._fullUrl);
                    }
                    
                    image.src = fullUrl2;
                    image._fullUrl = fullUrl2;
                    updateImageShadow(image);
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
}// ========== 跳过（无法定夺） ==========
async function skipImage() {
    if (!currentImage || !currentUser) return;
    if (reviewLocked) return;
    reviewLocked = true;
    if (reviewLockTimer) clearTimeout(reviewLockTimer);
    reviewLockTimer = setTimeout(function() { reviewLocked = false; reviewLockTimer = null; }, 10000);
    flashButton('skipBtn');
    
    // 同submitReview: 隐藏图片+显示转圈
    var image = document.getElementById('reviewImage');
    var noImage = document.getElementById('noImageHint');
    if (image) {
        image.style.display = 'none';
        image.classList.remove('loaded');
        image.classList.remove('enter');
    }
    if (noImage) noImage.style.display = 'none';
    var badge = document.getElementById('roleBadge');
    if (badge) badge.style.display = 'none';
    if (thumbnailAbortController) { thumbnailAbortController.abort(); thumbnailAbortController = null; }
    if (fullImageAbortController) { fullImageAbortController.abort(); fullImageAbortController = null; }
    showLoadingBar('跳过中...');
    
    try {
        await fetch(`/api/image/${currentImage.id}/review`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `user_id=${currentUser.id}&status=skip`
        });
        
        // 保存到历史
        historyStack.push(currentImage);
        
        // 重新加载
        await loadStats();
        await loadImage();
        
    } catch (e) {
        hideLoadingBar();
        console.error('跳过失败:', e);
    }
    reviewLocked = false;
}

// ========== 下载图片 ==========
function downloadImage() {
    if (!currentImage) return;
    flashButton('downloadBtn');
    
    var btn = document.getElementById('downloadBtn');
    var progress = document.getElementById('dlProgress');
    var text = document.getElementById('dlText');
    var fileName = currentImage.path ? currentImage.path.split(/[/\\]/).pop() : 'image_' + currentImage.id + '.jpg';
    var url = '/api/image/' + currentImage.id + '/download';
    
    // Mobile: 浏览器原生下载，由浏览器跟踪进度
    if (window.innerWidth <= 768 || !btn) {
        var link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        link.click();
        return;
    }
    
    // Desktop: 自定义进度条
    btn.disabled = true;
    text.textContent = '0%';
    progress.style.width = '0%';
    
    fetch(url)
        .then(function(resp) {
            if (!resp.ok) throw new Error('下载失败');
            var total = parseInt(resp.headers.get('content-length')) || 0;
            var loaded = 0;
            var reader = resp.body.getReader();
            var chunks = [];
            
            function readChunk() {
                return reader.read().then(function(result) {
                    if (result.done) {
                        var blob = new Blob(chunks);
                        var url2 = URL.createObjectURL(blob);
                        var link = document.createElement('a');
                        link.href = url2;
                        link.download = fileName;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        setTimeout(function() { URL.revokeObjectURL(url2); }, 1000);
                        
                        btn.disabled = false;
                        text.textContent = '下载';
                        progress.style.width = '0%';
                        return;
                    }
                    
                    chunks.push(result.value);
                    loaded += result.value.length;
                    if (total > 0) {
                        var pct = Math.round(loaded / total * 100);
                        text.textContent = pct + '%';
                        progress.style.width = pct + '%';
                    } else {
                        text.textContent = Math.round(loaded / 1024) + 'KB';
                        progress.style.width = Math.min(95, loaded / 10240) + '%';
                    }
                    
                    return readChunk();
                });
            }
            
            return readChunk();
        })
        .catch(function(e) {
            console.error('下载失败:', e);
            btn.disabled = false;
            text.textContent = '重试';
            progress.style.width = '0%';
            setTimeout(function() { text.textContent = '下载'; }, 2000);
        });
}

// ========== 图片加载错误 ==========
window.imageLoadError = function() {
    var noImage = document.getElementById('noImageHint');
    if (noImage) noImage.style.display = 'block';
    hideLoadingBar();
}

// ========== 更新当前图片角色徽标 ==========
function updateRoleBadge() {
    const badge = document.getElementById('roleBadge');
    if (!badge) return;
    var indicator = document.getElementById('loadingIndicator2');
    var isLoading = indicator && indicator.style.display && indicator.style.display !== 'none';
    if (currentImage && currentImage.role_name && !isLoading) {
        badge.textContent = currentImage.role_name;
        badge.style.display = '';
    } else {
        badge.style.display = 'none';
    }
}


// ========== 公告 ==========
async function checkNotice() {
    try {
        const response = await fetch('/api/settings/notice');
        const data = await response.json();
        if (!data.content) {
            document.getElementById('noticeBtn').style.display = 'none';
            return;
        }
        document.getElementById('noticeBtn').style.display = '';
        
        // Check if first visit or version changed
        var seenVersion = localStorage.getItem('review_notice_version');
        if (seenVersion !== data.version) {
            showNoticeModal();
            localStorage.setItem('review_notice_version', data.version);
        }
    } catch (e) {
        console.error('加载公告失败:', e);
    }
}

async function showNoticeModal() {
    const modal = document.getElementById('noticeModal');
    const content = document.getElementById('noticeContent');
    if (!modal) return;
    
    // Close other panels first
    closeRulePanel();
    closeRolePanel();
    
    if (content) content.innerHTML = '<p style="color:var(--text-muted);">加载中...</p>';
    
    try {
        const response = await fetch('/api/settings/notice');
        const data = await response.json();
        if (content) {
            content.innerHTML = data.content ? parseMarkdown(data.content) : '<p style="color:var(--text-muted);">暂无公告</p>';
        }
    } catch (e) {
        if (content) content.innerHTML = '<p style="color:var(--text-muted);">加载失败</p>';
    }
    
    modal.classList.add('open');
}

function closeNoticeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('noticeModal');
    if (modal) modal.classList.remove('open');
}

// ========== 修改昵称 ==========
function editNickname() {
    if (!currentUser) return;
    const input = document.getElementById('nicknameInput');
    const modal = document.getElementById('nicknameModal');
    const display = document.getElementById('currentNickDisplay');
    if (input) input.value = currentUser.nickname || '';
    if (display) display.textContent = currentUser.nickname || '匿名用户';
    if (modal) modal.classList.add('open');
    if (input) setTimeout(function() { input.focus(); input.select(); }, 100);
}

async function saveNickname() {
    const nickname = document.getElementById('nicknameInput').value.trim();
    if (!nickname || !currentUser) return;
    
    try {
        await fetch(`/api/user/${currentUser.id}/nickname`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ nickname })
        });
        
        currentUser.nickname = nickname;
        updateUserUI();
        closeNicknameModal();
    } catch (e) {
        alert('修改失败');
    }
}

function closeNicknameModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('nicknameModal');
    if (modal) modal.classList.remove('open');
}

// ========== 角色选择 ==========
function updatePanelOverlay() {
    var overlay = document.getElementById('panelOverlay');
    if (!overlay) return;
    var anyOpen = document.querySelector('.role-panel.open, .rule-panel.open');
    overlay.classList.toggle('visible', !!anyOpen);
}

async function showRoleModal() {
    closeRulePanel(); // close the other panel first
    const panel = document.getElementById('rolePanel');
    const roleList = document.getElementById('roleList');
    
    if (!panel) return;
    
    try {
        const response = await fetch('/api/roles');
        const roles = await response.json();
        
        if (roleList) roleList.innerHTML = '';
        
        if (!roles || roles.length === 0) {
            if (roleList) roleList.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px;">暂无角色配置</p>';
        } else {
            roles.forEach(role => {
                const item = document.createElement('div');
                item.className = 'role-item';
                item.onclick = () => selectRole(role.id);

                const avatar = role.avatar_path 
                    ? `<img src="/uploads/${role.avatar_path.split(/[/\\]/).pop()}" class="role-avatar" onerror="this.style.display='none'">`
                    : '<div class="role-avatar"></div>';
                
                item.innerHTML = `
                    ${avatar}
                    <span class="role-name">${role.name || ''}</span>
                    <span class="role-stats">${role.reviewed_images || 0}/${role.total_images || 0}</span>
                `;
                
                if (roleList) roleList.appendChild(item);
            });
        }
        
        panel.classList.add('open');
        updatePanelOverlay();
    } catch (e) {
        console.error('加载角色列表失败:', e);
    }
}

async function selectRole(roleId) {
    currentRoleId = roleId;
    closeRolePanel();
    
    // 清除历史
    historyStack = [];
    
    // 重新加载图片
    await loadStats();
    await loadImage();
}

function closeRoleModal() {
    closeRolePanel();
}

function closeRolePanel() {
    const panel = document.getElementById('rolePanel');
    if (panel) panel.classList.remove('open');
    updatePanelOverlay();
}

// ========== 图片详情 ==========
function showImageDetail() {
    if (!currentImage) return;
    
    const detailReviewCount = document.getElementById('detailReviewCount');
    const detailPassCount = document.getElementById('detailPassCount');
    const detailFailCount = document.getElementById('detailFailCount');
    const detailSkipCount = document.getElementById('detailSkipCount');
    const myStatus = document.getElementById('myStatus');
    const modal = document.getElementById('imageDetailModal');
    
    if (detailReviewCount) detailReviewCount.textContent = currentImage.review_count || 0;
    if (detailPassCount) detailPassCount.textContent = currentImage.pass_count || 0;
    if (detailFailCount) detailFailCount.textContent = currentImage.fail_count || 0;
    if (detailSkipCount) detailSkipCount.textContent = currentImage.skip_count || 0;
    
    if (!myStatus) return;
    if (currentImage.is_reviewed_by_user) {
        const statusMap = { pass: '已通过', fail: '未通过', skip: '已跳过' };
        myStatus.textContent = statusMap[currentImage.is_reviewed_by_user] || '';
        myStatus.className = 'detail-status ' + currentImage.is_reviewed_by_user;
    } else {
        myStatus.textContent = '尚未审核';
        myStatus.className = 'detail-status';
    }
    
    if (modal) modal.classList.add('open');
}

function closeImageDetailModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('imageDetailModal');
    if (modal) modal.classList.remove('open');
}

// ========== 审核要求 ==========
async function showRuleModal() {
    closeRolePanel(); // close the other panel first
    const panel = document.getElementById('rulePanel');
    const content = document.getElementById('ruleContent');
    
    if (!panel) return;
    
    if (content) content.innerHTML = '<p style="color:var(--text-muted);">加载中...</p>';
    
    try {
        const response = await fetch('/api/settings/review-rule');
        const data = await response.json();
        
        if (content) {
            content.innerHTML = parseMarkdown(data.content || '暂无审核要求');
        }
    } catch (e) {
        if (content) content.innerHTML = '<p style="color:var(--text-muted);">暂无审核要求</p>';
    }
    
    panel.classList.add('open');
    updatePanelOverlay();
}

function closeRuleModal() {
    closeRulePanel();
}

function closeRulePanel() {
    const panel = document.getElementById('rulePanel');
    if (panel) panel.classList.remove('open');
    updatePanelOverlay();
}

// 简单的Markdown解析（带XSS防护）
function parseMarkdown(text) {
    if (!text) return '';
    
    // 第〇步：提取 <details> 块，暂存为占位符
    var blocks = [];
    var counter = 0;
    text = text.replace(/<details>([\s\S]*?)<\/details>/g, function(m, inner) {
        var ph = '%%DETAILS_' + (counter++) + '%%';
        blocks.push(m);
        return ph;
    });
    
    // 第一步：HTML实体转义（防止XSS）
    var escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
    
    // 第二步：解析Markdown语法
    var result = escaped
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>')
        .replace(/&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
        .replace(/!\[([^\]]*)\]\(([^)=]+)(?:=(\d+)x(\d+))?\)/g, function(m, alt, url, w, h) {
            var s = 'max-width:100%;';
            if (w) s += 'width:' + w + 'px;';
            if (h) s += 'height:' + h + 'px;';
            return '<img src="' + url + '" alt="' + alt + '" style="' + s + '">';
        })
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
    
    // 第三步：包裹连续 <li> 为 <ul>（在换行转段落之前！）
    result = result.replace(/(<li>[\s\S]*?<\/li>(?:\s*<li>[\s\S]*?<\/li>)*)/g, '<ul>$1</ul>');
    
    // 第四步：换行转段落
    result = result
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
    
    // 连续图片组包裹（在换行转段落之后，允许中间有 <br>）
    result = result.replace(/(<img[^>]*>(?:\s*(?:<br>)?\s*<img[^>]*>)+)/g, '<div class="img-group">$1</div>');
    
    // 第六步：恢复 details 块
    for (var i = 0; i < blocks.length; i++) {
        var raw = blocks[i];
        // 提取 summary
        var summaryMatch = raw.match(/<summary>([\s\S]*?)<\/summary>/);
        var summaryHtml = summaryMatch ? '<summary>' + parseInlineMarkdown(summaryMatch[1]) + '</summary>' : '';
        // 提取 body（summary 后面的内容，去掉 </details>）
        var bodyStart = raw.indexOf('</summary>');
        var body = '';
        if (bodyStart >= 0) {
            body = raw.substring(bodyStart + 10);
            // 去掉末尾的 </details>
            var closeTag = body.lastIndexOf('</details>');
            if (closeTag >= 0) body = body.substring(0, closeTag);
        } else {
            body = raw.substring(8, raw.length - 9);
        }
        var bodyHtml = parseMarkdown(body);
        var html = '<details>' + summaryHtml + bodyHtml + '</details>';
        result = result.replace('%%DETAILS_' + i + '%%', html);
    }
    
    return result;
}

function parseInlineMarkdown(text) {
    return text
        .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>')
        .replace(/!\[([^\]]*)\]\(([^)=]+)(?:=(\d+)x(\d+))?\)/g, function(m, alt, url, w, h) {
            var s = 'max-width:100%;';
            if (w) s += 'width:' + w + 'px;';
            if (h) s += 'height:' + h + 'px;';
            return '<img src="' + url + '" alt="' + alt + '" style="' + s + '">';
        });
}

// ========== 页面加载时获取配置 ==========
// 全局配置
let appConfig = { required_votes: 3 };

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        // 更新页面标题
        if (data.title) {
            const titleEl = document.getElementById('pageTitle');
            if (titleEl) titleEl.textContent = data.title;
        }
        
        // 更新页面图标
        if (data.icon) {
            const iconEl = document.getElementById('pageIcon');
            if (iconEl) iconEl.href = data.icon;
        }
        
        // 获取投票配置
        try {
            const votesRes = await fetch('/api/settings/votes');
            if (!votesRes.ok) {
                let errorText = '';
                try {
                    errorText = await votesRes.text();
                } catch (_) { /* ignore body read errors */ }
                console.error('获取投票配置失败:', votesRes.status, votesRes.statusText, errorText);
            } else {
                const votesData = await votesRes.json();
                if (votesData.required_votes) {

                    appConfig.required_votes = votesData.required_votes;
                }
            }
        } catch (e) {
            console.log('使用默认投票数');
        }
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}

// ========== 点击图片显示详情 ==========
const reviewImage = document.getElementById('reviewImage');
if (reviewImage) {
    reviewImage.addEventListener('click', showImageDetail);
}

// ========== 点击模态框外部关闭 ==========
document.addEventListener('click', function(event) {
    ['rulePanel', 'rolePanel'].forEach(function(pid) {
        var panel = document.getElementById(pid);
        if (panel && panel.classList.contains('open')) {
            var rect = panel.getBoundingClientRect();
            var isMobile = window.innerWidth <= 768;
            // Desktop: click outside (left of panel)
            // Mobile: click on the dark overlay (the image area behind the panel)
            if ((!isMobile && event.clientX < rect.left) ||
                (isMobile && event.clientY < rect.top)) {
                if (pid === 'rulePanel') closeRulePanel();
                else closeRolePanel();
            }
        }
    });
});
window.onclick = function(event) {
    const modalIds = ['roleModal'];
    
    modalIds.forEach(id => {
        const modal = document.getElementById(id);
        if (modal && event.target === modal) {
            modal.classList.remove('open');
        }
    });
};

// ========== 移动端手势滑动切换 ==========
let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;
let isSwiping = false;
let touchHandled = false;  // 防止重复触发

document.addEventListener('touchstart', function(e) {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
    touchEndX = touchStartX;
    touchEndY = touchStartY;
    isSwiping = true;
    touchHandled = false;
}, { passive: true });

document.addEventListener('touchmove', function(e) {
    if (!isSwiping || touchHandled) return;
    touchEndX = e.changedTouches[0].screenX;
    touchEndY = e.changedTouches[0].screenY;
}, { passive: true });

document.addEventListener('touchend', function(e) {
    if (!isSwiping || touchHandled) return;
    
    touchHandled = true;
    isSwiping = false;
    
    const deltaX = touchEndX - touchStartX;
    const deltaY = touchEndY - touchStartY;
    const minSwipeDistance = 80;
    const maxVerticalRatio = 0.5;  // 垂直偏移不超过水平偏移的50%
    
    // 判断是否为主要水平滑动（排除垂直滑动）
    if (Math.abs(deltaX) > Math.abs(deltaY) * (1 + maxVerticalRatio) && Math.abs(deltaX) > minSwipeDistance) {
        if (deltaX > 0) {
            // 向右滑动：上一张
            prevImage();
        } else {
            // 向左滑动：跳过/下一张
            skipImage();
        }
    }
}, { passive: true });

document.addEventListener('touchcancel', function(e) {
    // 触摸被取消时重置状态
    isSwiping = false;
    touchHandled = false;
}, { passive: true });

// ========== 键盘快捷键 ==========
document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT') return;
    
    switch(e.key) {
        case 'ArrowLeft':
            prevImage();
            break;
        case 'ArrowRight':
            skipImage();
            break;
        case '1':
        case 'a':
        case 'A':
            submitReview('fail');
            break;
        case '2':
        case 'd':
        case 'D':
            submitReview('pass');
            break;
    }
});

