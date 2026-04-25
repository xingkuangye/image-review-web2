from playwright.sync_api import sync_playwright
import json

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            is_mobile=True,
            has_touch=True
        )
        page = context.new_page()
        page.goto('http://localhost:8000')
        page.wait_for_timeout(2000)
        
        # Check layout and styles
        results = page.evaluate('''() => {
            const container = document.querySelector('.image-container');
            const img = document.querySelector('#reviewImage');
            const nav = document.querySelector('.mobile-bottom-nav');
            
            if (!container || !nav) return { error: "Elements not found" };
            
            const containerRect = container.getBoundingClientRect();
            const navRect = nav.getBoundingClientRect();
            const computedStyle = window.getComputedStyle(container);
            
            return {
                container: {
                    bottom: containerRect.bottom,
                    boxSizing: computedStyle.boxSizing,
                    boxShadow: computedStyle.boxShadow,
                    height: containerRect.height,
                    maxHeight: computedStyle.maxHeight
                },
                nav: {
                    top: navRect.top,
                    height: navRect.height
                },
                isBlocked: containerRect.bottom > navRect.top,
                distance: navRect.top - containerRect.bottom
            }
        }''')
        
        with open('layout_results.json', 'w') as f:
            json.dump(results, f, indent=2)
            
        browser.close()

if __name__ == '__main__':
    run()