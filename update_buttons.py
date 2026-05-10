import re

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\css\style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改基础按钮样式 - 添加圆角
old_btn = '''/* ========== Button Styles ========== */
.btn {
    border: none;
    padding: 12px 24px;
    font-size: 16px;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
    font-weight: 500;
    letter-spacing: 1px;
}

.btn:active {
    transform: scale(0.95);
}

.btn-prev {
    position: absolute;
    left: 24px;
    top: 24px;
    background-color: rgba(51, 51, 51, 0.9);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    z-index: 50;
}

.btn-prev:hover {
    background-color: rgba(68, 68, 68, 0.95);
    border-color: rgba(255, 255, 255, 0.4);
}

.btn-skip {
    position: absolute;
    right: 24px;
    top: 24px;
    background-color: rgba(102, 102, 102, 0.9);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    z-index: 50;
}

.btn-skip:hover {
    background-color: rgba(119, 119, 119, 0.95);
    border-color: rgba(255, 255, 255, 0.4);
}

.btn-fail {
    position: absolute;
    left: 24px;
    bottom: 24px;
    background-color: rgba(211, 47, 47, 0.9);
    color: #fff;
    padding: 16px 40px;
    font-size: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    z-index: 50;
}

.btn-fail:hover {
    background-color: rgba(244, 67, 54, 0.95);
    border-color: rgba(255, 255, 255, 0.5);
    box-shadow: 0 4px 20px rgba(211, 47, 47, 0.4);
}

.btn-pass {
    position: absolute;
    right: 24px;
    bottom: 24px;
    background-color: rgba(56, 142, 60, 0.9);
    color: #fff;
    padding: 16px 40px;
    font-size: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    z-index: 50;
}

.btn-pass:hover {
    background-color: rgba(76, 175, 80, 0.95);
    border-color: rgba(255, 255, 255, 0.5);
    box-shadow: 0 4px 20px rgba(56, 142, 60, 0.4);
}

.btn-download {
    position: absolute;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background-color: rgba(25, 118, 210, 0.9);
    color: #fff;
    padding: 12px 28px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    z-index: 50;
}

.btn-download:hover {
    background-color: rgba(33, 150, 243, 0.95);
    border-color: rgba(255, 255, 255, 0.4);
}

.btn-role-select {
    position: absolute;
    right: 24px;
    bottom: 110px;
    background-color: rgba(51, 51, 51, 0.9);
    color: #fff;
    padding: 10px 20px;
    font-size: 14px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    z-index: 50;
}

.btn-role-select:hover {
    background-color: rgba(68, 68, 68, 0.95);
    border-color: rgba(255, 255, 255, 0.4);
}'''

new_btn = '''/* ========== Button Styles ========== */
.btn {
    border: none;
    padding: 12px 24px;
    font-size: 16px;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
    font-weight: 500;
    letter-spacing: 1px;
    border-radius: 12px;
    background-color: rgba(60, 60, 60, 0.8);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.btn:active {
    transform: scale(0.95);
}

.btn-prev {
    position: absolute;
    left: 24px;
    top: 24px;
    background-color: rgba(80, 80, 80, 0.85);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.15);
    z-index: 50;
    border-radius: 12px;
}

.btn-prev:hover {
    background-color: rgba(100, 100, 100, 0.9);
    border-color: rgba(255, 255, 255, 0.25);
}

.btn-skip {
    position: absolute;
    right: 24px;
    top: 24px;
    background-color: rgba(90, 90, 90, 0.85);
    color: #e0e0e0;
    border: 1px solid rgba(255, 255, 255, 0.15);
    z-index: 50;
    border-radius: 12px;
}

.btn-skip:hover {
    background-color: rgba(110, 110, 110, 0.9);
    border-color: rgba(255, 255, 255, 0.25);
}

.btn-fail {
    position: absolute;
    left: 24px;
    bottom: 24px;
    background-color: rgba(180, 50, 50, 0.85);
    color: #f5f5f5;
    padding: 16px 40px;
    font-size: 18px;
    border: 1px solid rgba(255, 80, 80, 0.3);
    z-index: 50;
    border-radius: 16px;
}

.btn-fail:hover {
    background-color: rgba(200, 60, 60, 0.9);
    border-color: rgba(255, 100, 100, 0.4);
    box-shadow: 0 4px 20px rgba(200, 50, 50, 0.4);
}

.btn-pass {
    position: absolute;
    right: 24px;
    bottom: 24px;
    background-color: rgba(50, 140, 60, 0.85);
    color: #f5f5f5;
    padding: 16px 40px;
    font-size: 18px;
    border: 1px solid rgba(80, 200, 100, 0.3);
    z-index: 50;
    border-radius: 16px;
}

.btn-pass:hover {
    background-color: rgba(60, 160, 70, 0.9);
    border-color: rgba(100, 220, 120, 0.4);
    box-shadow: 0 4px 20px rgba(60, 160, 70, 0.4);
}

.btn-download {
    position: absolute;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background-color: rgba(40, 100, 180, 0.85);
    color: #e8e8e8;
    padding: 12px 28px;
    border: 1px solid rgba(80, 140, 220, 0.25);
    z-index: 50;
    border-radius: 12px;
}

.btn-download:hover {
    background-color: rgba(50, 120, 200, 0.9);
    border-color: rgba(100, 160, 240, 0.35);
}

.btn-role-select {
    position: absolute;
    right: 24px;
    bottom: 110px;
    background-color: rgba(75, 60, 90, 0.85);
    color: #e0e0e0;
    padding: 10px 20px;
    font-size: 14px;
    border: 1px solid rgba(150, 120, 180, 0.25);
    z-index: 50;
    border-radius: 12px;
}

.btn-role-select:hover {
    background-color: rgba(95, 80, 110, 0.9);
    border-color: rgba(170, 140, 200, 0.35);
}'''

if old_btn in content:
    content = content.replace(old_btn, new_btn)
    print('按钮样式已更新')
else:
    print('未找到目标按钮样式')

with open(r'C:\Users\Admin\.minimax-agent-cn\projects\13\github-image-review\static\css\style.css', 'w', encoding='utf-8') as f:
    f.write(content)
