# -*- coding: utf-8 -*-

with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add completeCount and totalImages variables
old_vars = '''const progressPercent = document.getElementById('progressPercent');
        const progressFill = document.getElementById('progressFill');
        const reviewedCount = document.getElementById('reviewedCount');
        const totalCount = document.getElementById('totalCount');
        const userReviewCount = document.getElementById('userReviewCount');'''

new_vars = '''const progressPercent = document.getElementById('progressPercent');
        const progressFill = document.getElementById('progressFill');
        const reviewedCount = document.getElementById('reviewedCount');
        const totalCount = document.getElementById('totalCount');
        const userReviewCount = document.getElementById('userReviewCount');
        const completeCount = document.getElementById('completeCount');
        const totalImages = document.getElementById('totalImages');'''

if old_vars in content:
    content = content.replace(old_vars, new_vars)
    print("Fixed: Added variables")
else:
    print("ERROR: Variables pattern not found")

# Fix 2: Add completeCount and totalImages updates
old_updates = '''if (totalCount) totalCount.textContent = stats.total_images || 0;
        
        // 更新用户审核数'''

new_updates = '''if (totalCount) totalCount.textContent = stats.total_images || 0;
        
        // 更新完成审核数
        if (completeCount) completeCount.textContent = stats.completed_images || 0;
        if (totalImages) totalImages.textContent = stats.total_images || 0;
        
        // 更新用户审核数'''

if old_updates in content:
    content = content.replace(old_updates, new_updates)
    print("Fixed: Added completeCount updates")
else:
    print("ERROR: Updates pattern not found")

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
