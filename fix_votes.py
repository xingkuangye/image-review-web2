# -*- coding: utf-8 -*-

with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Use config API for votes instead of hardcoding 3
old_loadSettings = '''async function loadSettings() {
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
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}'''

new_loadSettings = '''// 全局配置
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
            const votesData = await votesRes.json();
            if (votesData.required_votes) {
                appConfig.required_votes = votesData.required_votes;
            }
        } catch (e) {
            console.log('使用默认投票数');
        }
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}'''

if old_loadSettings in content:
    content = content.replace(old_loadSettings, new_loadSettings)
    print("Fixed: Added appConfig and votes API call")
else:
    print("ERROR: loadSettings pattern not found")

# Also fix the totalCount display
old_total = '''// 投票进度条显示总票数 = 图片数 × 3
        if (totalCount) totalCount.textContent = (stats.total_images || 0) * 3;'''

new_total = '''// 投票进度条显示总票数 = 图片数 × 每张图片需要的票数
        if (totalCount) totalCount.textContent = (stats.total_images || 0) * appConfig.required_votes;'''

if old_total in content:
    content = content.replace(old_total, new_total)
    print("Fixed: totalCount now uses appConfig.required_votes")
else:
    print("ERROR: totalCount pattern not found")

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
