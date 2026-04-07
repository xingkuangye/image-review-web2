# -*- coding: utf-8 -*-

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Add margin to image-container in mobile to avoid being covered by bottom nav
# Find the mobile 768px media query section and add padding to main-content

old_main_mobile = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 100px);
        padding: 10px;
    }'''

new_main_mobile = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 100px);
        padding: 60px 10px 10px 10px;
    }'''

if old_main_mobile in content:
    content = content.replace(old_main_mobile, new_main_mobile)
    print("Fixed: main-content padding (768px)")
else:
    print("ERROR: 768px main-content pattern not found")

# Also fix 480px
old_main_480 = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 10px;
    }'''

new_main_480 = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 60px 10px 10px 10px;
    }'''

if old_main_480 in content:
    content = content.replace(old_main_480, new_main_480)
    print("Fixed: main-content padding (480px)")
else:
    print("ERROR: 480px main-content pattern not found")

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
