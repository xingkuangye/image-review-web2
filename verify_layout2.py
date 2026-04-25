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
            const mainContent = document.querySelector('.main-content');
            const container = document.querySelector('.image-container');
            const nav = document.querySelector('.mobile-bottom-nav');
            const navbar = document.querySelector('.navbar');
            
            const mcRect = mainContent.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();
            const navRect = nav.getBoundingClientRect();
            const navbarRect = navbar.getBoundingClientRect();
            
            const getStyle = (el) => {
                const s = window.getComputedStyle(el);
                return {
                    height: s.height,
                    maxHeight: s.maxHeight,
                    boxSizing: s.boxSizing,
                    padding: s.padding,
                    margin: s.margin
                };
            };
            
            return {
                viewport: { w: window.innerWidth, h: window.innerHeight },
                navbar: { rect: navbarRect, style: getStyle(navbar) },
                mainContent: { rect: mcRect, style: getStyle(mainContent) },
                container: { rect: containerRect, style: getStyle(container) },
                nav: { rect: navRect, style: getStyle(nav) },
                cssVars: {
                    contentHeight: window.getComputedStyle(document.documentElement).getPropertyValue('--mobile-content-height'),
                    navHeight: window.getComputedStyle(document.documentElement).getPropertyValue('--mobile-bottom-nav-height'),
                    headerHeight: window.getComputedStyle(document.documentElement).getPropertyValue('--mobile-header-height')
                }
            }
        }''')
        
        with open('layout_results2.json', 'w') as f:
            json.dump(results, f, indent=2)
            
        browser.close()

if __name__ == '__main__':
    run()