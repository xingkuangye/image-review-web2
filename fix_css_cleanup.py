# -*- coding: utf-8 -*-

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove redundant max-height: none; and use CSS variables for navbar height
old_root = '''/* ========== 基础样式 ========== */
:root {
    --mobile-button-offset: 140px;
    --mobile-top-padding: 60px;
}'''

new_root = '''/* ========== 基础样式 ========== */
:root {
    --mobile-button-offset: 140px;
    --navbar-height: 60px;
    --navbar-height-mobile: 50px;
}'''

if old_root in content:
    content = content.replace(old_root, new_root)
    print("Fixed: Added CSS variables for navbar height")
else:
    print("ERROR: :root pattern not found")

# Fix 2: Update 768px main-content
old_main_768 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 10px;
        align-items: flex-start;
        justify-content: center;
    }'''

new_main_768 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - var(--navbar-height-mobile));
        padding: 10px;
        align-items: flex-start;
        justify-content: center;
    }'''

if old_main_768 in content:
    content = content.replace(old_main_768, new_main_768)
    print("Fixed: main-content (768px)")
else:
    print("ERROR: main-content 768px pattern not found")

# Fix 3: Update 768px #reviewImage - remove redundant max-height: none;
old_img_768 = '''    #reviewImage {
        max-height: none;
        max-height: calc(100vh - 200px);
    }'''

new_img_768 = '''    #reviewImage {
        max-height: calc(100vh - 200px);
    }'''

if old_img_768 in content:
    content = content.replace(old_img_768, new_img_768)
    print("Fixed: #reviewImage (768px)")
else:
    print("ERROR: #reviewImage 768px pattern not found")

# Fix 4: Update 480px main-content
old_main_480 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - 60px);
        padding: 8px;
        align-items: flex-start;
        justify-content: center;
    }'''

new_main_480 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - var(--navbar-height-mobile));
        padding: 8px;
        align-items: flex-start;
        justify-content: center;
    }'''

if old_main_480 in content:
    content = content.replace(old_main_480, new_main_480)
    print("Fixed: main-content (480px)")
else:
    print("ERROR: main-content 480px pattern not found")

# Fix 5: Update 480px #reviewImage - remove redundant max-height: none;
old_img_480 = '''    #reviewImage {
        max-height: none;
        max-height: calc(100vh - 180px);
    }'''

new_img_480 = '''    #reviewImage {
        max-height: calc(100vh - 180px);
    }'''

if old_img_480 in content:
    content = content.replace(old_img_480, new_img_480)
    print("Fixed: #reviewImage (480px)")
else:
    print("ERROR: #reviewImage 480px pattern not found")

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
