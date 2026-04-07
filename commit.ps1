git add -A
git commit -m "Fix: refresh role images validation and scan path check

- refresh_role_images: check if path exists before deleting old images
- scan_and_add_images: add path validation to prevent os.walk hanging
- Both functions now return early with error log if path is invalid"
git push
