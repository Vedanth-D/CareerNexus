from playwright.sync_api import Page

def fill_field(page: Page, selector: str, value: str):
    try:
        el = page.query_selector(selector)
        if el and value:
            el.fill(value)
            return True
    except Exception as e:
        print(f"  Could not fill {selector}: {e}")
    return False

def upload_file(page: Page, file_path: str):
    try:
        el = page.query_selector('input[type="file"]')
        if el:
            el.set_input_files(file_path)
            return True
    except Exception as e:
        print(f"  Could not upload file: {e}")
    return False

def click_button(page: Page, selectors: list):
    for selector in selectors:
        try:
            el = page.query_selector(selector)
            if el:
                el.click()
                return True
        except:
            continue
    return False

def take_screenshot(page: Page, path: str = "debug_screenshot.png"):
    try:
        page.screenshot(path=path)
        print(f"  Screenshot saved to {path}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")