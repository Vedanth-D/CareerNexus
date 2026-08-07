import os
import tempfile
from playwright.sync_api import sync_playwright
from tools.browser_tools import fill_field, upload_file, click_button, take_screenshot
from core.state import AgentState

def browser_agent(state: AgentState) -> AgentState:
    job = state.get("current_job")
    if not job:
        print("Browser: No job to apply to, skipping.")
        return state

    print(f"\n🌐 Browser: Opening LinkedIn for {job['title']} at {job['company']}...")
    print("⚠️  You will need to log in to LinkedIn manually when the browser opens.")

    resume_text = state.get("tailored_resume", state["resume_profile"])
    tmp_resume = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(resume_text)
            tmp_resume = f.name

        with sync_playwright() as p:
            # Opens a VISIBLE browser window so you can log in
            browser = p.chromium.launch(headless=False, slow_mo=800)
            context = browser.new_context()
            page = context.new_page()

            # Step 1 — Go to LinkedIn login page
            print("  Opening LinkedIn login page...")
            page.goto("https://www.linkedin.com/login", timeout=30000)

            # Step 2 — Wait for YOU to log in manually
            print("\n" + "="*50)
            print("👉 ACTION NEEDED:")
            print("   Log in to LinkedIn in the browser window")
            print("   After login, the agent will continue automatically")
            print("="*50 + "\n")

            # Wait until LinkedIn home page loads after login
            page.wait_for_url("https://www.linkedin.com/feed/", timeout=120000)
            print("✅ LinkedIn login detected! Agent taking over...")

            # Step 3 — Navigate to the job
            page.goto(job["url"], timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            take_screenshot(page, "debug_job_page.png")
            print(f"  Opened job page for: {job['title']}")

            # Step 4 — Click Easy Apply button
            applied = click_button(page, [
                'button:has-text("Easy Apply")',
                'button:has-text("Apply")',
                '.jobs-apply-button',
                '[data-control-name="jobdetails_topcard_inapply"]',
            ])

            if applied:
                print("  ✅ Clicked Apply button!")
                page.wait_for_timeout(2000)
                take_screenshot(page, "debug_apply_form.png")

                # Step 5 — Fill the form
                _fill_linkedin_form(page, state)

                print("\n" + "="*50)
                print("👉 REVIEW THE FORM in the browser window")
                print("   The agent has filled what it can.")
                print("   Check everything looks correct.")
                print("   Press ENTER here when ready to close.")
                print("="*50)
                input()

            else:
                print("  ❌ Could not find Apply button")
                print("  Check debug_job_page.png to see what the page looks like")
                take_screenshot(page, "debug_no_apply.png")

            browser.close()

        applied_ids = state.get("applied_jobs", []) + [job["id"]]
        return {**state, "applied_jobs": applied_ids}

    except Exception as e:
        print(f"  Browser error: {e}")
        return {**state, "errors": state.get("errors", []) + [str(e)]}

    finally:
        if tmp_resume and os.path.exists(tmp_resume):
            os.unlink(tmp_resume)


def _fill_linkedin_form(page, state):
    """Try to fill common LinkedIn Easy Apply form fields"""
    cover_letter = state.get("cover_letter", "")

    # Phone number
    fill_field(page, 
        'input[id*="phoneNumber"], input[name*="phone"]',
        "+91 99999 99999")

    # Cover letter text area
    fill_field(page,
        'textarea[id*="cover"], textarea[name*="cover"]',
        cover_letter)

    # Years of experience fields (LinkedIn often asks this)
    for exp_field in page.query_selector_all('input[id*="experience"]'):
        try:
            exp_field.fill("2")
        except:
            pass

    # Yes/No radio buttons — select Yes by default
    for radio in page.query_selector_all('input[type="radio"][value="Yes"]'):
        try:
            radio.click()
        except:
            pass

    print("  ✅ Form fields filled")