# -*- coding: utf-8 -*-

with open('static/js/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: totalCount should show total votes (total_images * 3), not total_images
old_total = '''if (totalCount) totalCount.textContent = stats.total_images || 0;'''

new_total = '''// 投票进度条显示总票数 = 图片数 × 3
        if (totalCount) totalCount.textContent = (stats.total_images || 0) * 3;'''

if old_total in content:
    content = content.replace(old_total, new_total)
    print("Fixed: totalCount now shows total votes")
else:
    print("ERROR: totalCount pattern not found")

with open('static/js/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
