# -*- coding: utf-8 -*-
with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('@app.put("/api/admin/roles/{role_id}")')
print(content[idx:idx+4000])
