// ========== 全局状态 ==========
let adminToken = null;
// 使用sessionStorage存储，页面关闭后自动清除，比localStorage更安全

// ========== 认证辅助函数 ==========
function ensureAdminToken() {
    // 从sessionStorage或localStorage读取token
    const token = sessionStorage.getItem('admin_session') || localStorage.getItem('admin_session');
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
    // 尝试从存储恢复token
    adminToken = sessionStorage.getItem('admin_session') || localStorage.getItem('admin_session');
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
            var remember = document.getElementById('rememberMe') && document.getElementById('rememberMe').checked;
            if (remember) {
                // 持久化登录：localStorage + 7天
                localStorage.setItem('admin_session', password);
                localStorage.setItem('admin_expire', Date.now() + 604800000);
            } else {
                // 会话登录：sessionStorage + 1小时
                sessionStorage.setItem('admin_session', password);
                sessionStorage.setItem('admin_expire', Date.now() + 3600000);
            }
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
    var expireTime = sessionStorage.getItem('admin_expire') || localStorage.getItem('admin_expire');
    if (expireTime && Date.now() > parseInt(expireTime)) {
        logout();
        return;
    }
    
    // 如果没有本地token，跳转到登录
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
            var ext = sessionStorage.getItem('admin_session') ? 3600000 : 604800000;
            var store = sessionStorage.getItem('admin_session') ? sessionStorage : localStorage;
            store.setItem('admin_expire', Date.now() + ext);
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
    localStorage.removeItem('admin_session');
    localStorage.removeItem('admin_expire');
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
        case 'health':
            loadHealth();
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
        document.getElementById('settingNotice').value = data.notice || '';
    } catch (e) {
        console.error('加载设置失败:', e);
    }
}

async function saveSettings() {
    const title = document.getElementById('settingTitle').value.trim();
    const icon = document.getElementById('settingIcon').value.trim();
    const reviewRule = document.getElementById('settingReviewRule').value.trim();
    const notice = document.getElementById('settingNotice').value.trim();
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
        
        // 保存公告
        await adminFetch('/api/admin/settings/notice', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'content=' + encodeURIComponent(notice)
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

// ========== 用户图表 ==========
let usersChartInstance = null;

async function loadUsersChart() {
    if (typeof Chart === 'undefined') return;
    try {
        const response = await adminFetch('/api/admin/users/daily-stats');
        const data = await response.json();
        
        const ctx = document.getElementById('usersChart');
        if (!ctx) return;
        
        if (usersChartInstance) usersChartInstance.destroy();
        
        // Format dates for display (MM/DD)
        const labels = data.dates.map(function(d) {
            var parts = d.split('-');
            return parts[1] + '/' + parts[2];
        });
        
        // Only show every 5th label on x-axis
        const displayLabels = labels.map(function(l, i) {
            return i % 5 === 0 ? l : '';
        });
        
        usersChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: displayLabels,
                datasets: [{
                    label: '活跃用户',
                    data: data.active,
                    borderColor: '#5b8def',
                    backgroundColor: 'rgba(91, 141, 239, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                }, {
                    label: '新用户',
                    data: data.new_users,
                    borderColor: '#4ade80',
                    backgroundColor: 'rgba(74, 222, 128, 0.08)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: {
                            color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || 'rgba(240,242,248,0.65)',
                            font: { size: 11 },
                            boxWidth: 12,
                            padding: 16,
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(18,22,38,0.9)',
                        titleFont: { size: 12 },
                        bodyFont: { size: 11 },
                        padding: 10,
                        cornerRadius: 8,
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: {
                            color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || 'rgba(240,242,248,0.4)',
                            font: { size: 10 },
                            maxRotation: 0,
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: {
                            color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || 'rgba(240,242,248,0.4)',
                            font: { size: 10 },
                            stepSize: 1,
                            precision: 0,
                        }
                    }
                }
            }
        });
    } catch (e) {
        console.error('加载用户图表失败:', e);
    }
}

// ========== 用户管理 ==========
async function recalcCredibility() {
    if (!confirm('重新计算所有用户可信度？\n此操作可能需要几秒钟。')) return;
    try {
        await adminFetch('/api/admin/credibility/recalc', { method: 'POST' });
        alert('可信度已重新计算');
        loadUsers();
    } catch (e) {
        alert('计算失败');
    }
}

async function loadUsers() {
    loadUsersChart();
    const sortBy = document.getElementById('userSort').value;
    
    try {
        const [usersRes, credRes] = await Promise.all([
            adminFetch(`/api/admin/users?sort_by=${sortBy}`),
            adminFetch('/api/admin/credibility')
        ]);
        const users = await usersRes.json();
        const credData = await credRes.json();
        var credMap = {};
        if (credData && credData.users) {
            credData.users.forEach(function(c) { credMap[c.user_id] = c; });
        }
        
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
                <div class="user-cred">
                    <div class="cred-badge">${formatCred(credMap[user.id])}</div>
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
        document.getElementById('totalVotes').textContent = stats.total_votes || 0;
        document.getElementById('totalCompleted').textContent = stats.completed_images;
        document.getElementById('totalPass').textContent = stats.pass_count || 0;
        document.getElementById('totalFail').textContent = stats.fail_count || 0;
        
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
                    <button class="btn btn-small" onclick="showRoleImages(${item.role.id},\'${escapeHtml(item.role.name)}\')" style="margin-top:8px;">查看详情</button>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('加载统计失败:', e);
    }
}

// ========== 角色图片详情 ==========
async function showRoleImages(roleId, roleName) {
    document.getElementById('roleImagesTitle').textContent = roleName + ' - 图片审核状态';
    document.getElementById('roleImagesPanel').style.display = 'block';
    document.getElementById('roleImagesList').innerHTML = '<p style="padding:20px;color:var(--text-muted);text-align:center;">加载中...</p>';
    try {
        const response = await adminFetch('/api/admin/role-images/' + roleId);
        const data = await response.json();
        renderRoleImages(data.images);
    } catch (e) {
        document.getElementById('roleImagesList').innerHTML = '<p style="padding:20px;color:var(--accent-red);text-align:center;">加载失败</p>';
    }
}
function closeRoleImages() {
    document.getElementById('roleImagesPanel').style.display = 'none';
}
function renderRoleImages(images) {
    var container = document.getElementById('roleImagesList');
    if (!images || images.length === 0) {
        container.innerHTML = '<p style="padding:30px;color:var(--text-muted);text-align:center;">暂无图片</p>';
        return;
    }
    container.innerHTML = images.map(function(img) {
        var statusBadge, badgeClass;
        if (img.status === 'completed') {
            statusBadge = img.resolution === 'pass' ? '已通过' : '未通过';
            badgeClass = 'badge badge-' + (img.resolution === 'pass' ? 'pass' : 'fail');
        } else {
            statusBadge = '审核中 ' + img.total_weight.toFixed(1) + '/4.0';
            badgeClass = 'badge badge-pending';
        }
        var votersHtml = img.voters.map(function(v) {
            var vicon = v.vote === 'pass' ? '\u2714' : v.vote === 'fail' ? '\u2718' : '\u2014';
            var vcls = 'voter ' + (v.vote === 'pass' ? 'v-pass' : v.vote === 'fail' ? 'v-fail' : 'v-skip');
            var uid = v.user_id ? v.user_id.substring(0, 8) : '';
            return '<div class="' + vcls + '"><span class="v-icon">' + vicon + '</span><span class="v-name">' + escapeHtml(v.nickname) + '</span><span class="v-uid">#' + escapeHtml(uid) + '</span><span class="v-cred">' + (v.cred * 100).toFixed(0) + '%</span></div>';
        }).join('');
        var imgId = img.id;
        var failSvg = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 150"><rect fill="#1a1a2e" width="260" height="150"/><text x="130" y="75" text-anchor="middle" fill="#555" font-size="13">\u65e0\u56fe</text></svg>');
        return '<div class="rimg-card"><div class="rimg-img"><img src="/api/image/' + imgId + '/thumbnail?t=' + imgId + '" loading="lazy" onerror="this.src=\'' + failSvg + '\'"></div><div class="rimg-body"><div class="rimg-hdr"><span class="rimg-id">#' + imgId + '</span><span class="' + badgeClass + '">' + statusBadge + '</span></div><div class="rimg-bar"><div class="rimg-bar-fill rimg-bar-pass" style="flex:' + Math.max(img.w_pass, 0.01) + '"></div><div class="rimg-bar-fill rimg-bar-fail" style="flex:' + Math.max(img.w_fail, 0.01) + '"></div></div><div class="rimg-weights"><span class="w-pass">\u2705 ' + img.w_pass.toFixed(1) + '</span><span class="w-fail">\u274c ' + img.w_fail.toFixed(1) + '</span></div><div class="rimg-voters">' + votersHtml + '</div></div></div>';
    }).join('');
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

// ========== 系统健康检查 ==========
async function restartServer() {
    if (!confirm('确认要重启后端服务吗？\n页面将暂时无法访问，约等待3-5秒后自动恢复。')) return;
    try {
        await adminFetch('/api/admin/restart', { method: 'POST' });
        alert('服务正在重启...\n请等待几秒后重新加载页面。');
        setTimeout(function() { location.reload(); }, 3000);
    } catch (e) {
        // 重启后请求会中断，这是正常的
        setTimeout(function() { location.reload(); }, 3000);
    }
}

async function loadHealth() {
    const container = document.getElementById('healthContent');
    container.innerHTML = '<div class="health-loading">检查中...</div>';
    
    try {
        const response = await adminFetch('/api/admin/health');
        const data = await response.json();
        renderHealth(container, data);
    } catch (e) {
        console.error('健康检查失败:', e);
        container.innerHTML = '<div class="health-error">无法连接到服务器</div>';
    }
}

function renderHealth(container, data) {
    function badge(ok, okText, errText) {
        return ok
            ? '<span class="health-badge health-ok">' + (okText || '正常') + '</span>'
            : '<span class="health-badge health-err">' + (errText || '异常') + '</span>';
    }
    function latBadge(ms) {
        if (ms < 5) return '<span class="health-badge health-ok">' + ms + 'ms</span>';
        if (ms < 20) return '<span class="health-badge health-warn">' + ms + 'ms</span>';
        return '<span class="health-badge health-err">' + ms + 'ms</span>';
    }

    var db = data.database;
    var st = data.storage;
    var mem = data.memory;
    var cpu = data.cpu;
    var net = data.network;
    var imgs = data.images;
    var dirs = data.directories;
    var srv = data.server;
    var dirLabels = {data:'数据', uploads:'上传', thumbnails:'缩略图', backups:'备份'};

    var stUsage = st.usage_percent;
    var stColor = 'health-ok';
    if (stUsage > 85) stColor = 'health-err';
    else if (stUsage > 65) stColor = 'health-warn';

    var memUsage = mem ? mem.usage_percent : 0;
    var memColor = 'health-ok';
    if (memUsage > 85) memColor = 'health-err';
    else if (memUsage > 65) memColor = 'health-warn';

    var memHtml = mem ? [
        '<div class="health-row"><span class="health-label">已用</span><span>' + mem.used_formatted + ' / ' + mem.total_formatted + '</span></div>',
        '<div class="health-row"><span class="health-label">可用</span><span>' + mem.available_formatted + '</span></div>',
        '<div class="health-progress-section"><div class="health-progress-bar"><div class="health-progress-fill ' + memColor + '" style="width:' + memUsage + '%"></div></div><span class="health-progress-text">' + memUsage + '%</span></div>',
        (mem.swap_total > 0 ? '<div class="health-row"><span class="health-label">交换</span><span>' + mem.swap_used_formatted + ' / ' + mem.swap_total_formatted + '</span></div>' : '')
    ].join('') : '<div class="health-card-body"><div class="health-row"><span>-</span></div></div>';

    var cpuHtml = cpu ? [
        '<div class="health-row"><span class="health-label">核心数</span><span>' + cpu.cores + ' 核</span></div>',
        '<div class="health-row"><span class="health-label">负载 1min</span><span>' + cpu.load_1min + '</span></div>',
        '<div class="health-row"><span class="health-label">负载 5min</span><span>' + cpu.load_5min + '</span></div>',
        '<div class="health-row"><span class="health-label">负载 15min</span><span>' + cpu.load_15min + '</span></div>'
    ].join('') : '<div class="health-card-body"><div class="health-row"><span>-</span></div></div>';

    container.innerHTML = '<div class="health-grid">'
        + '<div class="health-card health-card-wide"><div class="health-card-title">服务器</div><div class="health-card-body">'
            + '<div class="health-row"><span class="health-label">主机名</span><span>' + escapeHtml(srv.hostname) + '</span></div>'
            + '<div class="health-row"><span class="health-label">系统</span><span>' + escapeHtml(srv.platform) + '</span></div>'
            + '<div class="health-row"><span class="health-label">Python</span><span>' + escapeHtml(srv.python_version) + '</span></div>'
            + '<div class="health-row"><span class="health-label">运行时间</span><span>' + escapeHtml(srv.uptime_formatted) + '</span></div>'
        + '</div></div>'

        + '<div class="health-card"><div class="health-card-title">数据库 <span class="health-subtitle">SQLite ' + escapeHtml(db.version || '') + '</span></div><div class="health-card-body">'
            + '<div class="health-row"><span class="health-label">状态</span><span>' + (db.ok ? '<span class="health-badge health-ok">正常</span>' : '<span class="health-badge health-err">异常</span>') + '</span></div>'
            + '<div class="health-row"><span class="health-label">延迟</span><span>' + latBadge(db.latency_ms) + '</span></div>'
            + '<div class="health-row"><span class="health-label">大小</span><span>' + db.size_formatted + '</span></div>'
        + '</div><div class="health-card-sub">'
            + '<div class="health-stat"><span class="health-num">' + db.tables.images + '</span> 图片</div>'
            + '<div class="health-stat"><span class="health-num">' + db.tables.reviews + '</span> 审核</div>'
            + '<div class="health-stat"><span class="health-num">' + db.tables.users + '</span> 用户</div>'
            + '<div class="health-stat"><span class="health-num">' + db.tables.roles + '</span> 角色</div>'
        + '</div></div>'

        + '<div class="health-card"><div class="health-card-title">存储</div><div class="health-card-body">'
            + '<div class="health-row"><span class="health-label">已用</span><span>' + st.used_formatted + ' / ' + st.total_formatted + '</span></div>'
            + '<div class="health-row"><span class="health-label">剩余</span><span>' + st.free_formatted + '</span></div>'
            + '<div class="health-progress-section"><div class="health-progress-bar"><div class="health-progress-fill ' + stColor + '" style="width:' + stUsage + '%"></div></div><span class="health-progress-text">' + stUsage + '%</span></div>'
        + '</div></div>'

        + '<div class="health-card"><div class="health-card-title">网络</div><div class="health-card-body">'
            + '<div class="health-row"><span class="health-label">DNS 解析</span><span>' + badge(net.dns, '正常', '异常') + '</span></div>'
            + '<div class="health-row"><span class="health-label">外网连通</span><span>' + badge(net.connectivity, '正常', '异常') + '</span></div>'
        + '</div></div>'

        + '<div class="health-card"><div class="health-card-title">图片完整性</div><div class="health-card-body">'
            + '<div class="health-row"><span class="health-label">图片总数</span><span>' + imgs.total + '</span></div>'
            + '<div class="health-row"><span class="health-label">缺失样本</span><span>' + (imgs.missing_sample > 0
                ? '<span class="health-badge health-err">' + imgs.missing_sample + ' 张</span>'
                : '<span class="health-badge health-ok">无</span>') + '</span></div>'
        + '</div></div>'

        + '<div class="health-card"><div class="health-card-title">内存</div>'
            + (mem ? '<div class="health-card-body">' + memHtml + '</div>' : memHtml)
        + '</div>'

        + '<div class="health-card"><div class="health-card-title">CPU</div>'
            + (cpu ? '<div class="health-card-body">' + cpuHtml + '</div>' : cpuHtml)
        + '</div>'

        + '<div class="health-card health-card-wide"><div class="health-card-title">目录状态</div>'
        + '<div class="health-dir-grid">'
            + Object.entries(dirs).map(function(kv) {
                var name = kv[0], dir = kv[1];
                var ok = dir.exists && dir.writable;
                var st = ok ? '<span class="health-badge health-ok">正常</span>' : '<span class="health-badge health-err">异常</span>';
                return '<div class="health-dir-item"><div class="health-row"><span class="health-label">' + (dirLabels[name] || name) + '</span><span>' + st + '</span></div><div class="health-dir-path">' + escapeHtml(dir.path) + '</div></div>';
            }).join('')
        + '</div></div>'
    + '</div>';
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

function formatCred(cred) {
    if (!cred || !cred.total || cred.total === 0) return '--';
    var pct = Math.round(cred.score * 100);
    var color = pct >= 80 ? 'var(--accent-green)' : pct >= 60 ? 'var(--accent-amber)' : 'var(--accent-red)';
    return '<span style="color:' + color + ';font-weight:600;font-size:14px;">' + pct + '%</span><span style="font-size:10px;color:var(--text-muted);display:block;">' + cred.agrees + '/' + cred.total + '</span>';
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
