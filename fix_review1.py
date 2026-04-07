# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: completed_images - add pass_count >= REQUIRED_VOTES to exclude skip-only cases
old_completed = '''COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count = 0 THEN image_id END) as completed_images'''

new_completed = '''COUNT(DISTINCT CASE WHEN vote_count >= ? AND pass_count >= ? AND fail_count = 0 THEN image_id END) as completed_images'''

if old_completed in content:
    content = content.replace(old_completed, new_completed)
    print("Fixed: completed_images now requires pass_count >= REQUIRED_VOTES")
else:
    print("ERROR: completed_images pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
