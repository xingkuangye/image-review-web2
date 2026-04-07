# -*- coding: utf-8 -*-

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Change main-content to align items from top on mobile, not center
old_main_768 = '''    /* 主内容区 - 减小顶部padding让图片更靠上 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 40px 10px 10px 10px;
    }'''

new_main_768 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 10px;
        align-items: flex-start;
        justify-content: center;
    }'''

if old_main_768 in content:
    content = content.replace(old_main_768, new_main_768)
    print("Fixed: main-content (768px)")
else:
    print("ERROR: main-content 768px pattern not found")

old_main_480 = '''    /* 主内容区 - 减小顶部padding让图片更靠上 */
    .main-content {
        height: calc(100vh - 60px);
        padding: 30px 8px 8px 8px;
    }'''

new_main_480 = '''    /* 主内容区 - 图片从顶部开始 */
    .main-content {
        height: calc(100vh - 60px);
        padding: 8px;
        align-items: flex-start;
        justify-content: center;
    }'''

if old_main_480 in content:
    content = content.replace(old_main_480, new_main_480)
    print("Fixed: main-content (480px)")
else:
    print("ERROR: main-content 480px pattern not found")

# Also update image-container to take more vertical space
old_image_768 = '''    /* 图片容器 - 更大显示空间 */
    .image-container {
        max-width: 95%;
        max-height: 55vh;
        padding: 10px;
    }
    
    #reviewImage {
        max-height: 55vh;
    }'''

new_image_768 = '''    /* 图片容器 - 从顶部开始，占满宽度 */
    .image-container {
        max-width: 95%;
        max-height: none;
        flex: 1;
        width: 100%;
        padding: 10px;
    }
    
    #reviewImage {
        max-height: none;
        max-height: calc(100vh - 200px);
    }'''

if old_image_768 in content:
    content = content.replace(old_image_768, new_image_768)
    print("Fixed: image-container (768px)")
else:
    print("ERROR: image-container 768px pattern not found")

old_image_480 = '''    /* 图片容器 */
    .image-container {
        max-width: 98%;
        max-height: 45vh;
        padding: 8px;
    }
    
    #reviewImage {
        max-height: 45vh;
    }'''

new_image_480 = '''    /* 图片容器 - 从顶部开始 */
    .image-container {
        max-width: 98%;
        max-height: none;
        flex: 1;
        width: 100%;
        padding: 8px;
    }
    
    #reviewImage {
        max-height: none;
        max-height: calc(100vh - 180px);
    }'''

if old_image_480 in content:
    content = content.replace(old_image_480, new_image_480)
    print("Fixed: image-container (480px)")
else:
    print("ERROR: image-container 480px pattern not found")

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
