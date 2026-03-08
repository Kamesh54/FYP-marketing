import asyncio, os
from dotenv import load_dotenv
load_dotenv(r"c:\Users\kames\Downloads\agent-ta-thon (2)\agent-ta-thon\.env")
from playwright.async_api import async_playwright

USERNAME   = os.getenv("REDDIT_USERNAME", "")
PASSWORD   = os.getenv("REDDIT_PASSWORD", "")
SUBREDDIT  = "test"   # r/test is made for test posts
POST_TITLE = "Testing AI-powered marketing platform automation"
POST_BODY  = "Just testing our multi-agent content marketing platform that automates content creation, SEO optimization, and campaign scheduling. #AI #marketing"

async def run():
    print(f"Username: {USERNAME}  Password length: {len(PASSWORD)}")
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
            # ── 1. Log in ──────────────────────────────────────────────────
            print("Step 1: Opening login page...")
            await page.goto("https://old.reddit.com/login/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            await page.screenshot(path="reddit_login_page.png")

            print("Step 2: Entering username...")
            user_input = page.locator("#user_login").first
            await user_input.wait_for(state="visible", timeout=15000)
            await user_input.type(USERNAME, delay=80)

            print("Step 3: Entering password...")
            pw_input = page.locator("#passwd_login").first
            await pw_input.wait_for(state="visible", timeout=10000)
            await pw_input.type(PASSWORD, delay=80)

            print("Step 4: Clicking Log In...")
            login_btn = page.locator("button[type='submit'], input[type='submit']").first
            await login_btn.wait_for(state="visible", timeout=10000)
            await login_btn.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path="reddit_step4_after_login.png")
            print(f"URL after login: {page.url}")

            if "/login" in page.url or "/register" in page.url:
                print("Login may have failed — check reddit_step4_after_login.png")
                await browser.close()
                return

            print("Logged in!")

            # ── 2. Navigate to subreddit submit page ────────────────────────
            print(f"Step 5: Navigating to r/{SUBREDDIT} submit page...")
            await page.goto(f"https://old.reddit.com/r/{SUBREDDIT}/submit", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            await page.screenshot(path="reddit_step5_submit_page.png")

            # old.reddit.com: click the "Text" tab to get selftext post form
            print("Step 6: Clicking Text tab...")
            try:
                text_tab = page.locator("li.text-tab a, a[href*='selftext'], a:has-text('Text')").first
                if await text_tab.is_visible(timeout=3000):
                    await text_tab.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # ── 4. Fill in title ────────────────────────────────────────────
            print("Step 7: Entering title...")
            title_input = page.locator("input[name='title']").first
            await title_input.wait_for(state="visible", timeout=15000)
            await title_input.click()
            await title_input.type(POST_TITLE, delay=40)

            # ── 5. Fill in body ─────────────────────────────────────────────
            print("Step 8: Entering body...")
            body_input = page.locator("textarea[name='text']").first
            if await body_input.is_visible(timeout=3000):
                await body_input.click()
                await body_input.type(POST_BODY, delay=40)

            await page.wait_for_timeout(1000)
            await page.screenshot(path="reddit_step8_filled.png")

            # ── 6. Submit ───────────────────────────────────────────────────
            print("Step 9: Submitting post...")
            submit_btn = page.locator("button[type='submit'], input[type='submit'][value='submit']").first
            await submit_btn.wait_for(state="visible", timeout=10000)
            await submit_btn.click()

            await page.wait_for_timeout(4000)
            await page.screenshot(path="reddit_posted.png")
            print(f"Done! URL: {page.url}")

        except Exception as e:
            await page.screenshot(path="reddit_error.png")
            print(f"ERROR: {e}")
            raise
        finally:
            await browser.close()

asyncio.run(run())
