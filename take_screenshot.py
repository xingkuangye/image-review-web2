from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        # iPhone 13 Pro dimensions: 390x844
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            is_mobile=True,
            has_touch=True,
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
        )
        page = context.new_page()
        page.goto('http://localhost:8000')
        page.wait_for_timeout(2000) # wait for page load and any animations
        page.screenshot(path='mobile_screenshot.png')
        browser.close()

if __name__ == '__main__':
    run()