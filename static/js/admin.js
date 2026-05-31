// ========== 全局状态 ==========
// 使用sessionStorage存储，页面关闭后自动清除，比localStorage更安全

// ========== 认证辅助函数 ==========
function ensureAdminToken() {
    // 每次都从sessionStorage读取最新token
    const token = sessionStorage.getItem('admin_session');
    if (!token) {
        console.error('Admin token is missing.');
        throw new Error('Admin authentication required.');
    }
    return token;
}

// Helper for admin-authenticated requests
async function adminFetch(url, options = {}) {
    const token = ensureAdminToken();
    
    const headers = {
        ...(options.headers || {}),
        'X-Admin-Password': token
    };
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    // 集中处理认证失败
    if (response.status === 401 || response.status === 403) {
        console.error('Admin authentication failed or expired.');
        logout();
        throw new Error('Admin authentication failed.');
    }
    
    return response;
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
    if (adminToken) {
        verifyToken();
    }
});

// ========== 密码验证 ==========
async function verifyPassword() {
    const password = document.getElementById('adminPassword').value;
    if (!password) return;
    
    try {
        const response = await fetch('/api/admin/verify', {
            headers: {
                'X-Admin-Password': password
            }
        });
        const data = await response.json();
        
        if (data.valid) {
            adminToken = password;
            // 使用sessionStorage存储，浏览器/标签页关闭后自动清除
            sessionStorage.setItem('admin_session', password);
            // 设置1小时过期
            sessionStorage.setItem('admin_expire', Date.now() + 3600000);
            showAdminPage();
        } else {
            document.getElementById('loginError').style.display = 'block';
        }
    } catch (e) {
        console.error('验证失败:', e);
        document.getElementById('loginError').style.display = 'block';
    }
}

async function verifyToken() {
    // 优先检查本地过期时间（快速失败）
    const expireTime = sessionStorage.getItem('admin_expire');
    if (expireTime && Date.now() > parseInt(expireTime)) {
        logout();
        return;
    }
    
    // 如果没有本地token或已过期，都跳转到登录
    if (!adminToken) {
        return;
    }
    
    try {
        const response = await fetch('/api/admin/verify', {
            headers: {
                'X-Admin-Password': adminToken
            }
        });
        const data = await response.json();
        
        if (data.valid) {
            // 验证成功，顺延过期时间
            sessionStorage.setItem('admin_expire', Date.now() + 3600000);
            showAdminPage();
        } else {
            logout();
        }
    } catch (e) {
        logout();
    }
}

function logout() {
    adminToken = null;
    sessionStorage.removeItem('admin_session');
    sessionStorage.removeItem('admin_expire');
    document.getElementById('loginPage').style.display = 'block';
    document.getElementById('adminPage').style.display = 'none';
}

// ========== 页面切换 ==========
function showAdminPage() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('adminPage').style.display = 'block';
    loadRoles();
    loadUsers();
    loadStats();
    loadSettings();
}

function switchTab(tabName) {
    // 更新标签样式
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        }
    });
    
    // 更新内容显示
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById('tab-' + tabName).classList.add('active');
    
    // 加载对应数据
    switch(tabName) {
        case 'roles':
            loadRoles();
            break;
        case 'users':
            loadUsers();
            break;
        case 'stats':
            loadStats();
            break;
        case 'backup':
            loadBackupSettings();
            loadBackups();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

// ========== 设置管理 ==========
async function loadSettings() {
    try {
        const response = await adminFetch('/api/admin/settings');
        const data = await response.json();
        
        document.getElementById('settingTitle').value = data.title || '';
        document.getElementById('settingIcon').value = data.icon || '';
        document.getElementById('settingReviewRule').value = data.review_rule || '';
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

async function saveSettings() {
    const title = document.getElementById('settingTitle').value.trim();
    const icon = document.getElementById('settingIcon').value.trim();
    const reviewRule = document.getElementById('settingReviewRule').value.trim();
    const msgEl = document.getElementById('settingsMsg');
    
    try {
        // 保存标题
        await adminFetch('/api/admin/settings/title', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'title=' + encodeURIComponent(title)
        });
        
        // 保存图标
        await adminFetch('/api/admin/settings/icon', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'icon=' + encodeURIComponent(icon)
        });
        
        // 保存审核规则
        await adminFetch('/api/admin/settings/review-rule', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'content=' + encodeURIComponent(reviewRule)
        });
        
        msgEl.textContent = '保存成功！';
        msgEl.style.display = 'block';
        setTimeout(() => {
            msgEl.style.display = 'none';
        }, 3000);
        
    } catch (e) {
        console.error('保存设置失败:', e);
        msgEl.textContent = '保存失败';
        msgEl.style.color = '#f44336';
        msgEl.style.display = 'block';
    }
}

// ========== 角色管理 ==========

// ========== 文件夹选择功能 ==========

/**
 * 处理文件夹选择
 * @param {HTMLInputElement} input - 文件选择input元素
 * @param {string} targetInputId - 目标输入框ID
 */
function handleFolderSelect(input, targetInputId) {
    const targetInput = document.getElementById(targetInputId);
    if (!targetInput) {
        console.error('Target input element not found:', targetInputId);
        alert('Error: Target input field not found.');
        return;
    }
    
    const files = input.files;
    if (!files || files.length === 0) {
        return;
    }
    // Get first file path
        let folderPath = '';
        
        if (files[0].webkitRelativePath) {
            // 从webkitRelativePath提取文件夹路径
            // 例如: "images/role1/pic.jpg" -> "images/role1"
            const parts = files[0].webkitRelativePath.split('/');
            if (parts.length > 1) {
                parts.pop(); // 移除文件名
                folderPath = parts.join('/');
            }
        }
        
        // Try to extract folder path
        if (!folderPath && files[0].path) {
            // Electron environment
            const filePath = files[0].path;
            folderPath = filePath.substring(0, filePath.lastIndexOf(files[0].name));
            // Remove trailing slashes
            folderPath = folderPath.replace(/[\/\\]+$/, '');
        }
        
        // Prompt user if path cannot be obtained
        if (!folderPath) {
            // Browser security restriction
            alert('已选择 ' + files.length + ' 个文件\n\n由于浏览器安全限制，无法自动获取完整文件夹路径。\n请手动输入完整的文件夹路径。\n\n示例：\n- Windows: C:\\images\\role1\n- Mac/Linux: /home/user/images/role1');
        } else {
            targetInput.value = folderPath;
        }
        
        // Clear input for reuse
        input.value = '';
}

async function loadRoles() {
    try {
        const response = await adminFetch('/api/admin/roles');
        const roles = await response.json();
        
        const roleList = document.getElementById('roleList');
        
        if (roles.length === 0) {
            roleList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">暂无角色配置</p>';
            return;
        }
        
        roleList.innerHTML = roles.map(role => `
            <div class="role-item">
                ${role.avatar_path 
                    ? `<img src="/uploads/${role.avatar_path.split(/[/\\]/).pop()}" class="role-avatar">`
                    : '<div class="role-avatar"></div>'
                }
                <div class="role-info">
                    <div class="role-name">${escapeHtml(role.name)}</div>
                    <div class="role-path">${escapeHtml(role.image_path)}</div>
                </div>
                <div class="role-stats">
                    <div>${role.reviewed_images || 0}/${role.total_images || 0}</div>
                    <div>
                        <span class="pass">通过: ${role.pass_count || 0}</span> | 
                        <span class="fail">不通过: ${role.fail_count || 0}</span>
                    </div>
                </div>
                <div class="role-actions">
                    <button class="btn btn-small" onclick="showEditRoleModal(${role.id})">修改</button>
                    <button class="btn btn-small btn-warning" onclick="refreshRole(${role.id})">刷新</button>
                    <button class="btn btn-small btn-danger" onclick="deleteRole(${role.id})">删除</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载角色失败:', e);
    }
}

function showAddRoleModal() {
    document.getElementById('addRoleModal').style.display = 'block';
    document.getElementById('roleName').value = '';
    document.getElementById('rolePath').value = '';
    document.getElementById('roleAvatar').value = '';
}

function closeAddRoleModal() {
    document.getElementById('addRoleModal').style.display = 'none';
}

// 修改角色相关变量
let editRoleData = {};

async function showEditRoleModal(roleId) {
    try {
        const response = await adminFetch('/api/admin/roles');
        const roles = await response.json();
        const role = roles.find(r => r.id === roleId);
        
        if (role) {
            editRoleData[roleId] = role;
            document.getElementById('editRoleId').value = roleId;
            document.getElementById('editRoleName').value = role.name || '';
            document.getElementById('editRolePath').value = role.image_path || '';
            document.getElementById('editRoleAvatar').value = '';
            document.getElementById('editRoleModal').style.display = 'block';
        }
    } catch (e) {
        console.error('加载角色信息失败:', e);
    }
}

function closeEditRoleModal() {
    document.getElementById('editRoleModal').style.display = 'none';
}

async function updateRole() {
    const roleId = document.getElementById('editRoleId').value;
    const name = document.getElementById('editRoleName').value.trim();
    const path = document.getElementById('editRolePath').value.trim();
    const avatarFile = document.getElementById('editRoleAvatar').files[0];
    
    if (!name || !path) {
        alert('请填写角色名称和图片路径');
        return;
    }
    
    const role = editRoleData[roleId];
    
    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('image_path', path);
        formData.append('refresh_images', 'true');
        if (avatarFile) {
            formData.append('avatar', avatarFile);
        }
        
        const response = await adminFetch(`/api/admin/roles/${roleId}`, {
            method: 'PUT',
            body: formData
        });
        
        if (response.ok) {
            closeEditRoleModal();
            loadRoles();
        } else {
            alert('修改失败');
        }
    } catch (e) {
        console.error('修改角色失败:', e);
        alert('修改失败');
    }
}

async function addRole() {
    const name = document.getElementById('roleName').value.trim();
    const path = document.getElementById('rolePath').value.trim();
    const avatarFile = document.getElementById('roleAvatar').files[0];
    
    if (!name || !path) {
        alert('请填写角色名称和图片路径');
        return;
    }
    
    const formData = new FormData();
    formData.append('name', name);
    formData.append('image_path', path);
    if (avatarFile) {
        formData.append('avatar', avatarFile);
    }
    
    try {
        const response = await adminFetch('/api/admin/roles', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            closeAddRoleModal();
            loadRoles();
        } else {
            alert('添加失败');
        }
    } catch (e) {
        console.error('添加角色失败:', e);
        alert('添加失败');
    }
}

async function refreshRole(roleId) {
    try {
        const response = await adminFetch(`/api/admin/roles/${roleId}/refresh`, {
            method: 'POST'
        });
        
        if (response.ok) {
            loadRoles();
        }
    } catch (e) {
        console.error('刷新失败:', e);
    }
}

async function deleteRole(roleId) {
    if (!confirm('确定要删除此角色吗？')) return;
    
    try {
        const response = await adminFetch(`/api/admin/roles/${roleId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadRoles();
        }
    } catch (e) {
        console.error('删除失败:', e);
    }
}

// ========== 用户管理 ==========
async function loadUsers() {
    const sortBy = document.getElementById('userSort').value;
    
    try {
        const response = await adminFetch(`/api/admin/users?sort_by=${sortBy}`);
        const users = await response.json();
        
        const userList = document.getElementById('userList');
        
        if (users.length === 0) {
            userList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">暂无用户</p>';
            return;
        }
        
        userList.innerHTML = users.map(user => `
            <div class="user-item ${user.is_banned ? 'banned' : ''}">
                <div class="user-avatar">${user.nickname.charAt(0).toUpperCase()}</div>
                <div class="user-info">
                    <div class="user-nickname">${escapeHtml(user.nickname)}</div>
                    <div class="user-id">ID: ${user.id.substring(0, 8)}...</div>
                </div>
                <div class="user-stats">
                    <div class="count">${user.total_reviews}</div>
                    <div class="label">审核数</div>
                </div>
                <div class="user-last-active">
                    <div class="time">${formatTime(user.last_active)}</div>
                    <div class="label">最后上线</div>
                </div>
                <div class="user-status">
                    <span class="badge ${user.is_banned ? 'badge-banned' : 'badge-active'}">
                        ${user.is_banned ? '已封禁' : '正常'}
                    </span>
                </div>
                <div class="user-actions">
                    <button class="btn btn-small" onclick="showUserReviews('${user.id}')">查看</button>
                    <button class="btn btn-small btn-warning" onclick="clearUserReviews('${user.id}')">清除</button>
                    <button class="btn btn-small ${user.is_banned ? 'btn-success' : 'btn-danger'}" 
                            onclick="toggleBan('${user.id}', ${!user.is_banned})">
                        ${user.is_banned ? '解封' : '封禁'}
                    </button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载用户失败:', e);
    }
}

async function showUserReviews(userId) {
    try {
        const response = await adminFetch(`/api/admin/users/${userId}/reviews`);
        const reviews = await response.json();
        
        const reviewsList = document.getElementById('userReviewsList');
        
        if (reviews.length === 0) {
            reviewsList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">暂无审核记录</p>';
        } else {
            reviewsList.innerHTML = reviews.map(review => `
                <div class="review-item">
                    <img src="/api/image/${review.image_id}/download" class="review-thumb" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 80 60%22><rect fill=%22%23333%22 width=%2280%22 height=%2260%22/><text x=%2240%22 y=%2235%22 text-anchor=%22middle%22 fill=%22%23666%22 font-size=%2212%22>无图</text></svg>">
                    <div class="review-path" title="${escapeHtml(review.image_path)}">${escapeHtml(review.image_path)}</div>
                    <div class="review-status">
                        <span class="status status-${review.status}">${
                            review.status === 'pass' ? '通过' : 
                            review.status === 'fail' ? '不通过' : '跳过'
                        }</span>
                        <div class="review-time">${formatTime(review.reviewed_at)}</div>
                    </div>
                    <button class="btn btn-small btn-danger" onclick="deleteReview(${review.id})">删除</button>
                </div>
            `).join('');
        }
        
        document.getElementById('userReviewsModal').style.display = 'block';
    } catch (e) {
        console.error('加载审核记录失败:', e);
    }
}

function closeUserReviewsModal() {
    document.getElementById('userReviewsModal').style.display = 'none';
}

async function deleteReview(reviewId) {
    if (!confirm('确定要删除此审核记录吗？')) return;
    
    try {
        const response = await adminFetch(`/api/admin/reviews/${reviewId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadUsers();
        }
    } catch (e) {
        console.error('删除失败:', e);
    }
}

async function clearUserReviews(userId) {
    if (!confirm('确定要清除该用户的所有审核结果吗？')) return;
    
    try {
        const response = await adminFetch(`/api/admin/users/${userId}/reviews`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadUsers();
        }
    } catch (e) {
        console.error('清除失败:', e);
    }
}

async function toggleBan(userId, ban) {
    const action = ban ? '封禁' : '解封';
    if (!confirm(`确定要${action}该用户吗？`)) return;
    
    try {
        const formData = new FormData();
        formData.append('banned', ban);
        
        const response = await adminFetch(`/api/admin/users/${userId}/ban`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            loadUsers();
        }
    } catch (e) {
        console.error('操作失败:', e);
    }
}

// ========== 审核状况 ==========
async function loadStats() {
    try {
        const response = await adminFetch('/api/admin/stats');
        const data = await response.json();
        
        // 总体统计
        const stats = data.overall;
        document.getElementById('totalProgress').style.width = stats.progress_percent + '%';
        document.getElementById('totalProgressText').textContent = stats.progress_percent.toFixed(1) + '%';
        document.getElementById('totalImages').textContent = stats.total_images;
        document.getElementById('totalReviewed').textContent = stats.reviewed_images;
        document.getElementById('totalPass').textContent = stats.pass_count;
        document.getElementById('totalFail').textContent = stats.fail_count;
        
        // 角色统计
        const roleStatsList = document.getElementById('roleStatsList');
        
        if (data.roles.length === 0) {
            roleStatsList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">暂无角色统计</p>';
        } else {
            roleStatsList.innerHTML = data.roles.map(item => `
                <div class="role-stats-item">
                    <div class="role-stats-header">
                        <span class="role-stats-name">${escapeHtml(item.role.name)}</span>
                        <span class="role-stats-percent">${item.stats.progress_percent.toFixed(1)}%</span>
                    </div>
                    <div class="role-stats-bar">
                        <div class="role-stats-fill" style="width: ${item.stats.progress_percent}%"></div>
                    </div>
                    <div class="role-stats-details">
                        <span>总图片: ${item.stats.total_images}</span>
                        <span>已审核: ${item.stats.reviewed_images}</span>
                        <span class="text-pass">通过: ${item.stats.pass_count}</span>
                        <span class="text-fail">不通过: ${item.stats.fail_count}</span>
                    </div>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('加载统计失败:', e);
    }
}

// ========== 导出功能 ==========
async function exportApproved() {
    if (!confirm('确定要导出所有审核通过的图片吗？\n审核通过条件：至少5人投票，且通过>=3人\n图片将按角色分文件夹打包。')) return;
    
    const btn = event.target;
    btn.textContent = '导出中...';
    btn.disabled = true;
    
    try {
        const response = await adminFetch('/api/admin/export', {
            method: 'GET'
        });
        
        const contentType = response.headers.get('content-type') || '';
        
        if (contentType.includes('application/json')) {
            // 返回的是JSON，可能是没有图片
            const data = await response.json();
            alert(data.message || '暂无审核通过的图片');
        } else if (contentType.includes('application/zip') || contentType.includes('application/octet-stream')) {
            // 返回的是ZIP文件，下载
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '审核通过图片.zip';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } else {
            alert('导出失败，未知响应格式');
        }
    } catch (e) {
        console.error('导出失败:', e);
        alert('导出失败: ' + e.message);
    } finally {
        btn.textContent = '导出审核通过的图片';
        btn.disabled = false;
    }
}

// ========== 争议图片导出 ==========
async function exportDisputed() {
    if (!confirm('确定要导出所有有争议的图片吗？\n争议定义：3人投票意见不一致\n图片将按角色分文件夹打包。')) return;
    
    const btn = event.target;
    btn.textContent = '导出中...';
    btn.disabled = true;
    
    try {
        const response = await adminFetch('/api/admin/export-disputed', {
            method: 'GET'
        });
        
        const contentType = response.headers.get('content-type') || '';
        
        if (contentType.includes('application/json')) {
            const data = await response.json();
            alert(data.message || '暂无可导出图片');
        } else if (contentType.includes('application/zip') || contentType.includes('application/octet-stream')) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '争议图片.zip';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } else {
            alert('导出失败，未知响应格式');
        }
    } catch (e) {
        console.error('导出失败:', e);
        alert('导出失败: ' + e.message);
    } finally {
        btn.textContent = '导出争议图片';
        btn.disabled = false;
    }
}

// ========== 工具函数 ==========
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(isoString) {
    if (!isoString) return '未知';
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    
    // 超过30天显示日期
    if (diff > 30 * 24 * 60 * 60 * 1000) {
        return date.toLocaleDateString('zh-CN');
    }
    
    // 超过24小时显示天数
    if (diff > 24 * 60 * 60 * 1000) {
        return Math.floor(diff / (24 * 60 * 60 * 1000)) + '天前';
    }
    
    // 超过60分钟显示小时
    if (diff > 60 * 60 * 1000) {
        return Math.floor(diff / (60 * 60 * 1000)) + '小时前';
    }
    
    // 超过60秒显示分钟
    if (diff > 60 * 1000) {
        return Math.floor(diff / (60 * 1000)) + '分钟前';
    }
    
    return '刚刚';
}

// ========== 点击模态框外部关闭 ==========
window.onclick = function(event) {
    const modals = [
        document.getElementById('addRoleModal'),
        document.getElementById('userReviewsModal')
    ];
    
    modals.forEach(modal => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}

// ========== 回车登录 ==========
document.getElementById('adminPassword')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        verifyPassword();
    }
});

// ========== 备份管理 ==========

async function loadBackupSettings() {
    try {
        const response = await adminFetch('/api/admin/settings');
        const data = await response.json();
        
        document.getElementById('settingAutoBackupEnabled').checked = data.auto_backup_enabled !== 'false';
        document.getElementById('settingAutoBackupTime').value = data.auto_backup_time || '03:00';
        document.getElementById('settingBackupRetentionDays').value = data.backup_retention_days || '7';
    } catch (e) {
        console.error('加载备份设置失败:', e);
    }
}

async function saveAutoBackupEnabled() {
    const enabled = document.getElementById('settingAutoBackupEnabled').checked;
    try {
        await adminFetch('/api/admin/settings/auto-backup-enabled', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'enabled=' + enabled
        });
    } catch (e) {
        console.error('保存备份设置失败:', e);
    }
}

async function saveBackupSettings() {
    const backupTime = document.getElementById('settingAutoBackupTime').value;
    const retentionDays = document.getElementById('settingBackupRetentionDays').value;
    const msgEl = document.getElementById('backupSettingsMsg');
    
    try {
        await adminFetch('/api/admin/settings/auto-backup-time', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'backup_time=' + encodeURIComponent(backupTime)
        });
        
        await adminFetch('/api/admin/settings/backup-retention-days', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'days=' + retentionDays
        });
        
        msgEl.textContent = '保存成功！';
        msgEl.style.display = 'block';
        setTimeout(() => {
            msgEl.style.display = 'none';
        }, 3000);
    } catch (e) {
        console.error('保存备份设置失败:', e);
        msgEl.textContent = '保存失败';
        msgEl.style.color = '#f44336';
        msgEl.style.display = 'block';
    }
}

async function loadBackups() {
    const backupList = document.getElementById('backupList');
    
    try {
        const response = await adminFetch('/api/admin/backup/list');
        const data = await response.json();
        
        if (data.backups.length === 0) {
            backupList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">暂无备份记录</p>';
            return;
        }
        
        backupList.innerHTML = data.backups.map(backup => `
            <div class="backup-item">
                <div class="backup-info">
                    <div class="backup-name">${escapeHtml(backup.filename)}</div>
                    <div class="backup-meta">
                        <span>大小: ${formatBytes(backup.size)}</span>
                        <span>时间: ${formatBackupTime(backup.time)}</span>
                    </div>
                </div>
                <div class="backup-actions">
                    <button class="btn btn-small" onclick="restoreBackup('${escapeHtml(backup.filename)}')">还原</button>
                    <button class="btn btn-small btn-danger" onclick="deleteBackupFile('${escapeHtml(backup.filename)}')">删除</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载备份列表失败:', e);
        backupList.innerHTML = '<p style="padding:20px;color:#888;text-align:center;">加载失败</p>';
    }
}

async function manualBackup() {
    const btn = event.target;
    btn.textContent = '备份中...';
    btn.disabled = true;
    
    try {
        const response = await adminFetch('/api/admin/backup/now', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            alert('备份成功！');
            loadBackups();
        } else {
            alert('备份失败: ' + data.message);
        }
    } catch (e) {
        console.error('备份失败:', e);
        alert('备份失败');
    } finally {
        btn.textContent = '立即备份';
        btn.disabled = false;
    }
}

async function restoreBackup(filename) {
    if (!confirm('确定要还原到 "' + filename + '" 吗？\n还原前会先备份当前数据库。')) return;
    
    try {
        const response = await adminFetch('/api/admin/backup/restore/' + encodeURIComponent(filename), {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            alert('还原成功！');
        } else {
            alert('还原失败: ' + data.message);
        }
    } catch (e) {
        console.error('还原失败:', e);
        alert('还原失败');
    }
}

async function deleteBackupFile(filename) {
    if (!confirm('确定要删除 "' + filename + '" 吗？')) return;
    
    try {
        const response = await adminFetch('/api/admin/backup/' + encodeURIComponent(filename), {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            loadBackups();
        } else {
            alert('删除失败');
        }
    } catch (e) {
        console.error('删除失败:', e);
        alert('删除失败');
    }
}

function formatBackupTime(time) {
    const date = new Date(time);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
