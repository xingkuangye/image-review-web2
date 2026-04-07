# -*- coding: utf-8 -*-
with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find refresh role endpoint
if 'refresh' in content.lower():
    idx = content.find('@app.put("@app.put("/api/admin/roles')
    if idx == -1:
        idx = content.find('refresh')
    print("Around refresh:")
    start = max(0, idx - 50)
    end = min(len(content), idx + 1000)
    print(content[start:end])
