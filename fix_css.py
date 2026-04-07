# -*- coding: utf-8 -*-

with open('static/css/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Extract repeated padding into a shared class
# Step 1: Add shared class after :root
old_root = '''/* ========== 基础样式 ========== */
:root {
    --mobile-button-offset: 140px;
}'''

new_root = '''/* ========== 基础样式 ========== */
:root {
    --mobile-button-offset: 140px;
    --mobile-top-padding: 60px;
}'''

if old_root in content:
    content = content.replace(old_root, new_root)
    print("Fixed: Added CSS variable")
else:
    print("ERROR: :root pattern not found")

# Step 2: Replace 768px padding with var
old_768 = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 100px);
        padding: 60px 10px 10px 10px;
    }
    
    /* 图片容器 - 更大显示空间 */'''

new_768 = '''    /* 主内容区 - 使用共享CSS变量 */
    .main-content {
        height: calc(100vh - 100px);
        padding: var(--mobile-top-padding) 10px 10px 10px;
    }
    
    /* 图片容器 - 更大显示空间 */'''

if old_768 in content:
    content = content.replace(old_768, new_768)
    print("Fixed: 768px main-content padding")
else:
    print("ERROR: 768px pattern not found")

# Step 3: Replace 480px padding with var
old_480 = '''    /* 主内容区 */
    .main-content {
        height: calc(100vh - 80px);
        padding: 60px 10px 10px 10px;
    }
    
    /* 图片容器 */'''

new_480 = '''    /* 主内容区 - 使用共享CSS变量 */
    .main-content {
        height: calc(100vh - 80px);
        padding: var(--mobile-top-padding) 10px 10px 10px;
    }
    
    /* 图片容器 */'''

if old_480 in content:
    content = content.replace(old_480, new_480)
    print("Fixed: 480px main-content padding")
else:
    print("ERROR: 480px pattern not found")

with open('static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
