"""Test X/Twitter posting via Playwright browser automation."""
import asyncio, os
from pathlib import Path

os.chdir(Path(__file__).parent)
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

EMAIL    = os.getenv("TWITTER_EMAIL", "")
PASSWORD = os.getenv("TWITTER_PASSWORD", "")
TWEET    = "Testing our AI-powered marketing platform! Automating content creation and campaign scheduling. #AI #marketing #automation"
SESSION_FILE = Path("x_session.json")


async def post_to_x():
    print(f"Email: {EMAIL}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=80,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        ctx_opts = dict(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        if SESSION_FILE.exists():
            print("Reusing saved session...")
            ctx_opts["storage_state"] = str(SESSION_FILE)

        ctx  = await browser.new_context(**ctx_opts)
        page = await ctx.new_page()
        try:
            print("Loading X home...")
            await page.goto("https://x.com/home", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            if "/home" not in page.url:
                print("Not logged in - starting login flow...")
                await page.goto("https://x.com/i/flow/login", wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                email_input = page.locator("input[autocomplete='username']")
                await email_input.wait_for(state="visible", timeout=20000)
                await email_input.type(EMAIL, delay=100)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)
                try:
                    challenge = page.locator("input[data-testid='ocfEnterTextTextInput']")
                    if await challenge.is_visible(timeout=2000):
                        print("  Username challenge...")
                        await challenge.type("Ganesh89960598", delay=100)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass
                pw = page.locator("input[name='password']")
                await pw.wait_for(state="visible", timeout=20000)
                await pw.type(PASSWORD, delay=100)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(6000)
                print(f"URL after login: {page.url}")
                if "/home" not in page.url:
                    await page.screenshot(path="login_failed.png")
                    print("Login failed - check login_failed.png")
                    await browser.close()
                    return
                await ctx.storage_state(path=str(SESSION_FILE))
                print("Session saved to x_session.json")
            print(f"Logged in! URL: {page.url}")
            print("Opening compose modal...")
            compose_btn = page.locator("[data-testid='SideNav_NewTweet_Button']")
            await compose_btn.wait_for(state="visible", timeout=15000)
            await compose_btn.click()
            await page.wait_for_timeout(2000)
            print("Typing tweet...")
            tweet_box = page.locator("[data-testid='tweetTextarea_0']").first
            await tweet_box.wait_for(state="visible", timeout=10000)
            await tweet_box.click()
            await tweet_box.type(TWEET, delay=40)
            await page.wait_for_timeout(1000)
            print("Posting...")
            post_btn = page.locator("[data-testid='tweetButtonInline']").first
            await post_btn.wait_for(state="enabled", timeout=10000)
            await post_btn.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path="posted.png")
            print(f"Done! Check posted.png  |  URL: {page.url}")
        except Exception as e:
            await page.screenshot(path="error.png")
            print(f"ERROR: {e}  - check error.png")
            raise
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(post_to_x())
