# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: Update SQL parameters to include REQUIRED_VOTES for pass_count check
old_params = '''(REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP))'''

new_params = '''(REQUIRED_VOTES, REQUIRED_VOTES, REQUIRED_VOTES, REVIEW_STATUS_SKIP, REVIEW_STATUS_PASS, REVIEW_STATUS_FAIL, REVIEW_STATUS_SKIP))'''

if old_params in content:
    content = content.replace(old_params, new_params)
    print("Fixed: SQL parameters updated")
else:
    print("ERROR: SQL params pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
