import asyncio
import os
import unicodedata
from playwright.async_api import Page, TimeoutError
from src.scraper.core.browser import BrowserManager
from src.database.connection import get_settings

class TwitterSpider:
    def __init__(self, manager: BrowserManager):
        self.manager = manager
        self.settings = get_settings()
        self.state_file = "twitter_state.json"

    async def ensure_login(self, page: Page):
        """Ensures the user is logged into Twitter/X using shared state or UI login."""
        # Check if already logged in by looking for account switcher or search
        if await page.locator("[data-testid='SideNav_AccountSwitcher_Button']").count() > 0:
            print("✅ Already logged in (detected UI).")
            return

        print("🔵 Checking Twitter Login Status...")
        await page.goto("https://x.com/home", timeout=60000, wait_until='domcontentloaded')
        
        if await page.locator("[data-testid='SideNav_AccountSwitcher_Button']").count() > 0:
            print("✅ Session active via cookies.")
            return

        print("🔑 Session expired or missing. Initializing login flow...")
        await page.goto("https://x.com/login", timeout=60000)

        # Username
        try:
            username_input = await page.wait_for_selector("input[autocomplete='username'], input[name='text']", timeout=10000)
            await username_input.fill(self.settings.TWITTER_USER)
            
            next_btn = page.locator("button:has-text('Próximo'), button:has-text('Next')").first
            await next_btn.click()
        except TimeoutError:
            content = await page.content()
            if "Enter your email" in content or "phone number" in content:
                print("📧 Twitter is asking for email/phone verification. Filling...")
                email_input = await page.wait_for_selector("input[autocomplete='email'], input[name='text']", timeout=5000)
                await email_input.fill(self.settings.TWITTER_USER)
                await page.click("button:has-text('Next')")
            else:
                raise

        # Password
        await asyncio.sleep(2)
        password_input = await page.wait_for_selector("input[name='password'], input[type='password']", timeout=15000)
        await password_input.fill(self.settings.TWITTER_PASS)

        # Final Login Click
        await asyncio.sleep(1)
        login_buttons = page.locator("button:has-text('Entrar'), button:has-text('Log in')").first
        await login_buttons.click()

        await page.wait_for_selector("[data-testid='SideNav_AccountSwitcher_Button']", timeout=20000)
        print("✅ Login successful.")

        # Save state
        await page.context.storage_state(path=self.state_file)
        print("💾 Session saved.")

    async def scrape_post(self, link_data: dict):
        """Navigates directly to a tweet and captures it, handling login only if needed."""
        url = link_data.get('url')
        if not url:
             return {"status": "error", "error": "No URL provided"}

        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()

        try:
            # Force https and x.com to avoid redirects and Cloudflare issues
            if "twitter.com" in url:
                url = url.replace("twitter.com", "x.com")
            if url.startswith("http://"):
                url = url.replace("http://", "https://", 1)

            print(f"🔗 Navigating directly to {url}...")
            # Try direct navigation first
            response = await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            
            # If redirected to login, ensure login and try again
            if "x.com/login" in page.url or await page.locator("[data-testid='loginButton']").count() > 0:
                print("🔑 Redirected to login. Ensuring session...")
                await self.ensure_login(page)
                print(f"🔗 Retrying navigation to {url}...")
                await page.goto(url, timeout=90000, wait_until="networkidle")
            else:
                # Wait for content to stabilize
                await page.wait_for_load_state("networkidle", timeout=60000)

            # Check for 404 or prohibited content immediately
            # We check multiple patterns including the one reported by the user
            error_patterns = [
                "text='Hmm...this page doesn't exist'",
                "text='Página não encontrada'",
                "text='Ih, esta página não existe'",
                "text='Esta conta não existe'",
                "text='This account doesn\\'t exist'"
            ]
            
            for pattern in error_patterns:
                if await page.locator(pattern).count() > 0:
                    print(f"⚠️ Twitter error detected: {pattern}")
                    return {"status": "not_found", "error": "Tweet or account not found (404)"}

            page_title = await page.title()
            if "not found" in page_title.lower() or "página não encontrada" in page_title.lower():
                return {"status": "not_found", "error": "Tweet not found (404 Title)"}

            # Wait for either main content (the tweet text) OR a known error message
            # This avoids waiting for a 45s timeout on 404 pages
            try:
                # Combined selector: wait for tweet text OR the common error container
                # Twitter error messages usually appear in a span/div within a specific container
                await page.wait_for_selector("[data-testid='tweetText'], [data-testid='error-detail'], text='Ih, esta página não existe', text='Hmm...this page doesn\\'t exist'", timeout=30000)
            except TimeoutError:
                # If nothing appears in 30s, check again for error patterns manually
                print("⚠️ Timeout waiting for tweet or error. Checking patterns...")
                pass

            # Check for 404 or prohibited content
            for pattern in error_patterns:
                if await page.locator(pattern).count() > 0:
                    print(f"⚠️ Twitter error detected: {pattern}")
                    return {"status": "not_found", "error": "Tweet or account not found (404)"}

            # Extract content
            tweet_text = await page.locator("[data-testid='tweetText']").first.inner_text()
            
            # Normalize Unicode
            if tweet_text:
                tweet_text = unicodedata.normalize('NFKD', tweet_text).encode('ascii', 'ignore').decode('ascii')

            # Save results
            link_id = link_data.get('link_id', 'unknown')
            screenshot_path = f"captures/twitter_{link_id}.png"
            os.makedirs("captures", exist_ok=True)
            
            await page.screenshot(path=screenshot_path, full_page=False)
            
            txt_path = f"captures/twitter_{link_id}.txt"
            with open(txt_path, "w", encoding="utf-8-sig") as f:
                f.write(tweet_text)

            return {
                "text_content": tweet_text,
                "image_path": screenshot_path,
                "text_path": txt_path,
                "status": "success"
            }
        except Exception as e:
            print(f"❌ Error scraping tweet: {e}")
            await page.screenshot(path="error_twitter.png")
            return {"status": "error", "error": str(e)}
        finally:
            await context.close()
