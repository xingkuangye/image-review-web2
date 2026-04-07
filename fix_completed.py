# -*- coding: utf-8 -*-

with open('backend/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: completed_images should require ALL votes to be passes
# Current: vote_count >= 3 AND pass_count >= 3 (wrong - allows mixed votes)
# Correct: pass_count >= 3 AND fail_count = 0 (all votes are passes)

old_completed = '''COUNT(DISTINCT CASE WHEN vote_count >= ? AND pass_count >= ? THEN image_id END) as completed_images'''

new_completed = '''COUNT(DISTINCT CASE WHEN vote_count >= ? AND fail_count = 0 THEN image_id END) as completed_images'''

if old_completed in content:
    content = content.replace(old_completed, new_completed)
    print("Fixed: completed_images condition")
else:
    print("ERROR: completed_images pattern not found")

with open('backend/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
