# -*- coding: utf-8 -*-
with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('def scan_and_add_images')
print(repr(content[idx:idx+1500]))
