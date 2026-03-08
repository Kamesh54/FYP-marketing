import asyncio, os
from dotenv import load_dotenv
load_dotenv(r"c:\Users\kames\Downloads\agent-ta-thon (2)\agent-ta-thon\.env")
from playwright.async_api import async_playwright

EMAIL    = os.getenv("TWITTER_EMAIL", "")
USERNAME = os.getenv("TWITTER_USERNAME", "")
PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWEET    = "Testing our AI-powered marketing platform! Automating content creation and campaign scheduling. #AI #marketing #automation"

async def click_button(page, step):
    """Click the Next / Log in button — tries several known selectors."""
    for sel in [
        "button[data-testid='LoginForm_Login_Button']",
        "button[data-testid='ocfLoginNextButton']",
        "button[data-testid='LoginForm_Next_Button']",
        "div[data-testid='ocfLoginNextButton']",
        "button:has-text('Next')",
        "button:has-text('Log in')",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                print(f"  [{step}] clicking: {sel}")
                await btn.click()
                return
        except Exception:
            continue
    raise Exception(f"[{step}] Could not find Next/Login button")

async def run():
    print(f"Email: {EMAIL}  Username: {USERNAME}  Password length: {len(PASSWORD)}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=80,
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await ctx.new_page()
        try:
            # ── 1. Open login ──────────────────────────────────────────────
            print("Step 1: Opening login page...")
            await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # ── 2. Enter email → click Next ────────────────────────────────
            print("Step 2: Entering email...")
            email_input = page.locator("input[autocomplete='username']")
            await email_input.wait_for(state="visible", timeout=20000)
            await email_input.type(EMAIL, delay=80)
            await page.wait_for_timeout(400)
            await click_button(page, "after email")
            await page.wait_for_timeout(2500)

            # ── 3. Username challenge (if X asks for handle) ───────────────
            try:
                ch = page.locator("input[data-testid='ocfEnterTextTextInput']")
                if await ch.is_visible(timeout=2000):
                    print("Step 3: Username challenge...")
                    await ch.type(USERNAME, delay=80)
                    await click_button(page, "after username challenge")
                    await page.wait_for_timeout(3000)
                    await page.screenshot(path="step3_after_challenge.png")
                    print(f"  After challenge URL: {page.url}")
            except Exception:
                pass

            # ── 4. Enter password → click Log in ──────────────────────────
            print("Step 4: Entering password...")
            await page.screenshot(path="step4_before_pw.png")            # Dump all visible inputs to understand current state
            inputs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    name: i.name, type: i.type, visible: i.offsetParent !== null,
                    testid: i.getAttribute('data-testid'), autocomplete: i.autocomplete
                }));
            }""")
            print(f"  Inputs on page: {inputs}")            pw = page.locator("input[name='password']")
            await pw.wait_for(state="visible", timeout=25000)
            await pw.type(PASSWORD, delay=80)
            await page.wait_for_timeout(400)
            await click_button(page, "after password")
            await page.wait_for_timeout(5000)
            print(f"URL after login: {page.url}")

            if "/home" not in page.url:
                await page.screenshot(path="login_failed.png")
                print("Login failed — screenshot: login_failed.png")
                await browser.close()
                return

            print("Logged in successfully!")

            # ── 5. Close post-login popup ──────────────────────────────────
            print("Step 5: Closing popup if present...")
            for sel in [
                "button[aria-label='Close']",
                "div[role='dialog'] button[aria-label='Close']",
                "[data-testid='xMigrationBottomBar'] button",
                "[data-testid='app-bar-close']",
                "[data-testid='confirmationSheetCancel']",
                "button:has-text('Skip for now')",
                "button:has-text('Not now')",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1500):
                        print(f"  Closing popup: {sel}")
                        await btn.click()
                        await page.wait_for_timeout(800)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(1500)

            # ── 6. Click compose (Post) button ─────────────────────────────
            print("Step 6: Opening compose box...")
            for sel in [
                "[data-testid='SideNav_NewTweet_Button']",
                "a[href='/compose/post']",
                "button[aria-label='Post']",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        print(f"  Compose: {sel}")
                        await btn.click()
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(2000)

            # ── 7. Type the tweet ──────────────────────────────────────────
            print("Step 7: Typing tweet...")
            box = page.locator("[data-testid='tweetTextarea_0']").first
            await box.wait_for(state="visible", timeout=10000)
            await box.click()
            await box.type(TWEET, delay=40)
            await page.wait_for_timeout(1000)

            # ── 8. Click Post ──────────────────────────────────────────────
            print("Step 8: Posting...")
            post_btn = page.locator("[data-testid='tweetButtonInline']").first
            await post_btn.wait_for(state="enabled", timeout=10000)
            await post_btn.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path="posted.png")
            print(f"Done! URL: {page.url}")

        except Exception as e:
            await page.screenshot(path="error.png")
            print(f"ERROR: {e}")
            raise
        finally:
            await browser.close()

asyncio.run(run())