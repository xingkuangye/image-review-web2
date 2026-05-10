from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8000')
    page.wait_for_timeout(2000) # wait for JS and images
    
    width = page.evaluate("document.getElementById('reviewImage').naturalWidth")
    height = page.evaluate("document.getElementById('reviewImage').naturalHeight")
    shadow = page.evaluate("document.querySelector('.image-container').style.boxShadow")
    
    print(f"图片尺寸: {width} x {height}")
    print(f"当前阴影: {shadow}")
    
    page.screenshot(path="C:\\Users\\Admin\\.minimax-agent-cn\\projects\\13\\github-image-review\\shadow_test.png", full_page=False)
    browser.close()
