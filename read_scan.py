# -*- coding: utf-8 -*-
with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def scan_and_add_images')
print(content[idx:idx+2000])
