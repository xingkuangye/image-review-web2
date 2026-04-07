# -*- coding: utf-8 -*-

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Reduce navbar padding on mobile to give more space to images
old_navbar_768 = '''/* 平板竖屏 (768px 以下) */
@media screen and (max-width: 768px) {
    /* 导航栏调整 */
    .navbar {
        flex-wrap: wrap;
        height: auto;
        min-height: 60px;
        padding: 10px 12px;
        gap: 10px;
    }'''

new_navbar_768 = '''/* 平板竖屏 (768px 以下) */
@media screen and (max-width: 768px) {
    /* 导航栏调整 - 减小内边距给图片更多空间 */
    .navbar {
        flex-wrap: wrap;
        height: auto;
        min-height: 50px;
        padding: 6px 10px;
        gap: 6px;
    }'''

if old_navbar_768 in content:
    content = content.replace(old_navbar_768, new_navbar_768)
    print("Fixed: navbar padding (768px)")
else:
    print("ERROR: navbar pattern not found")

# Reduce main-content top padding on mobile
old_main_768 = '''    /* 主内容区 - 使用共享CSS变量 */
    .main-content {
        height: calc(100vh - 100px);
        padding: var(--mobile-top-padding) 10px 10px 10px;
    }'''

new_main_768 = '''    /* 主内容区 - 减小顶部padding让图片更靠上 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 40px 10px 10px 10px;
    }'''

if old_main_768 in content:
    content = content.replace(old_main_768, new_main_768)
    print("Fixed: main-content padding (768px)")
else:
    print("ERROR: main-content 768px pattern not found")

# Reduce progress-container padding
old_progress_768 = '''    .progress-container {
        max-width: 200px;
    }
    
    .progress-label {
        font-size: 12px;
    }
    
    .complete-container {
        font-size: 12px;
        padding: 4px 10px;
        margin-left: 10px;
        margin-top: 8px;
        width: 100%;
        justify-content: center;
    }'''

new_progress_768 = '''    .progress-container {
        max-width: 180px;
    }
    
    .progress-label {
        font-size: 11px;
    }
    
    .complete-container {
        font-size: 11px;
        padding: 3px 8px;
        margin-left: 8px;
        margin-top: 4px;
        width: 100%;
        justify-content: center;
    }'''

if old_progress_768 in content:
    content = content.replace(old_progress_768, new_progress_768)
    print("Fixed: progress-container (768px)")
else:
    print("ERROR: progress-container pattern not found")

# Also update 480px section
old_main_480 = '''    /* 主内容区 - 使用共享CSS变量 */
    .main-content {
        height: calc(100vh - 80px);
        padding: var(--mobile-top-padding) 10px 10px 10px;
    }'''

new_main_480 = '''    /* 主内容区 - 减小顶部padding让图片更靠上 */
    .main-content {
        height: calc(100vh - 60px);
        padding: 30px 8px 8px 8px;
    }'''

if old_main_480 in content:
    content = content.replace(old_main_480, new_main_480)
    print("Fixed: main-content padding (480px)")
else:
    print("ERROR: main-content 480px pattern not found")

# Reduce 480px navbar
old_navbar_480 = '''/* 手机竖屏 (480px 以下) */
@media screen and (max-width: 480px) {
    /* 导航栏进一步简化 */
    .navbar {
        padding: 8px 10px;
    }'''

new_navbar_480 = '''/* 手机竖屏 (480px 以下) */
@media screen and (max-width: 480px) {
    /* 导航栏进一步简化 */
    .navbar {
        padding: 5px 8px;
    }'''

if old_navbar_480 in content:
    content = content.replace(old_navbar_480, new_navbar_480)
    print("Fixed: navbar padding (480px)")
else:
    print("ERROR: navbar 480px pattern not found")

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
