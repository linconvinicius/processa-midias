import asyncio
import os
import unicodedata
from playwright.async_api import Page, TimeoutError
from src.scraper.core.browser import BrowserManager
from src.database.connection import get_settings

class InstagramSpider:
    def __init__(self, manager: BrowserManager):
        self.manager = manager
        self.settings = get_settings()
        self.state_file = "instagram_state.json"

    async def ensure_login(self, page: Page):
        """Logs into Instagram if not already logged in."""
        try:
            await page.goto("https://www.instagram.com/")
            
            # Check for home/nav indicators (Search icon, Profile icon, etc.)
            try:
                # Search SVG or Profile Link
                await page.wait_for_selector("svg[aria-label='Pesquisa'], svg[aria-label='Search']", timeout=8000)
                print("✅ Already logged in to Instagram.")
                return
            except TimeoutError:
                print("🔄 Not logged in. Starting login flow...")

            # Wait for form
            await page.wait_for_selector("input[name='username']", timeout=10000)
            
            # Fill credentials
            await page.fill("input[name='username']", self.settings.INSTAGRAM_USER)
            await asyncio.sleep(1) # Human delay
            await page.fill("input[name='password']", self.settings.INSTAGRAM_PASS)
            await asyncio.sleep(1)
            
            # Click Login
            await page.click("button[type='submit']")
            
            # Wait for login success indicators (Save Info prompt or Home)
            try:
                await page.wait_for_selector("svg[aria-label='Pesquisa'], svg[aria-label='Search'], text='Agora não'", timeout=15000)
                print("✅ Login successful.")
                
                # Save state
                await page.context.storage_state(path=self.state_file)
                print("💾 Session saved.")
            except TimeoutError:
                print("❌ Login submitted but home screen not detected (2FA or Ban?).")
                raise
            
        except Exception as e:
            print(f"❌ Login failed: {e}")
            raise

    async def scrape_post(self, link_data: dict):
        """Navigates to an Instagram post and captures it."""
        url = link_data.get('url')
        if not url:
             return {"status": "error", "error": "No URL provided"}

        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()
        
        # Set a standard desktop viewport to match the user's pattern
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        try:
            await self.ensure_login(page)
            
            print(f"🔗 Navigating to {url}...")
            
            # Clean URL to avoid direct deep linking issues
            clean_url = url.split("?")[0] if "?" in url else url
            await page.goto(clean_url)
            
            # Wait for main content
            try:
                await page.wait_for_selector("main[role='main'], article, div.x1yvgwvq", timeout=45000)
            except TimeoutError:
                content = await page.content()
                if "Esta página não está disponível" in content or "Page Not Found" in content:
                     print("⚠️ Post deleted or not found.")
                     return {"status": "not_found", "error": "Content deleted or unavailable"}
                raise
            
            # Locate the container for scrolling/box calculation
            if await page.locator("article").count() > 0:
                article = page.locator("article").first
            elif await page.locator("div.x1yvgwvq").count() > 0:
                article = page.locator("div.x1yvgwvq").first
            else:
                article = page.locator("main[role='main']")
                
            # Path setup
            link_id = link_data.get('link_id', 'unknown')
            image_path = f"captures/instagram_{link_id}.png"
            text_path = f"captures/instagram_{link_id}.txt"
            os.makedirs("captures", exist_ok=True)

            print(f"📸 Preparing for pattern-match screenshot...")
            
            # DISMISS MODALS EARLY (Before waiting for selectors)
            try:
                await page.evaluate("""() => {
                    // Try to click 'X' (Close) button if it exists
                    const closeBtn = document.querySelector('div[role="button"] svg[aria-label="Fechar"], div[role="button"] svg[aria-label="Close"]')?.closest('div[role="button"]');
                    if (closeBtn) closeBtn.click();
                    
                    // Hide common fixed overlays immediately (darkened or white)
                    document.querySelectorAll('div').forEach(div => {
                        const s = window.getComputedStyle(div);
                        if (s.position === 'fixed' && parseInt(s.zIndex) > 0) {
                            if (s.backgroundColor.includes('rgba(0, 0, 0') || s.backgroundColor.includes('255, 255, 255') || s.backgroundColor === 'white') {
                                if (parseInt(s.width) > 400 && parseInt(s.height) > 400) {
                                    div.style.setProperty('display', 'none', 'important');
                                }
                            }
                        }
                    });
                    document.body.style.setProperty('overflow', 'visible', 'important');
                }""")
            except: pass

            # TRIGGER LAZY LOADING & WAIT FOR CONTENT
            print(f"📸 Preparing for pattern-match screenshot...")
            
            # Use mouse wheel to trigger rendering
            try:
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(0.5)
                await page.mouse.wheel(0, -500)
                await asyncio.sleep(0.5)
            except: pass

            # ---------------------------------------------------------
            # SURGICAL CLEANUP & STABILIZATION
            # ---------------------------------------------------------
            try:
                # Execute precise surgical cleanup for the target element and the whole page
                await page.evaluate("""(sel) => {
                    // 1. Force remove ALL filters, blurs and login walls via global CSS
                    const style = document.createElement('style');
                    style.id = 'scraping-final-cleanup';
                    style.innerHTML = `
                        * { 
                            filter: none !important; 
                            -webkit-filter: none !important; 
                            backdrop-filter: none !important;
                            -webkit-backdrop-filter: none !important;
                            mask: none !important;
                            -webkit-mask: none !important;
                        }
                        body, html {
                            overflow: visible !important;
                            filter: none !important;
                            background-color: white !important;
                            height: auto !important;
                            position: static !important;
                        }
                        /* Hide intrusive headers/footers/login prompts but KEEP sidebar legend */
                        nav, header, [role="banner"], section._aa-- { display: none !important; }
                        
                        /* Ensure the Reel/Post area is bright and ignore any dimming classes */
                        .x1yvgwvq, article {
                            opacity: 1 !important;
                            visibility: visible !important;
                            filter: none !important;
                            display: flex !important;
                        }
                        /* Hide overlay play buttons */
                        .x1yc453h, ._a9-6, ._a9-7, ._a9-8 { display: none !important; }
                    `;
                    document.head.appendChild(style);

                    // 2. Surgical removal of dimmed overlays (black or white fixed layers)
                    document.querySelectorAll('div').forEach(div => {
                        const s = window.getComputedStyle(div);
                        if (s.position === 'fixed' || s.position === 'absolute') {
                            const bg = s.backgroundColor;
                            if (bg.includes('rgba(0, 0, 0') || bg.includes('rgb(0, 0, 0)') || bg.includes('255, 255, 255') || bg === 'white') {
                                // Remove if it covers a significant area but doesn't contain the reel
                                if (parseInt(s.width) > 400 && !div.contains(document.querySelector('.x1yvgwvq')) && !div.contains(document.querySelector('article'))) {
                                    div.remove();
                                }
                            }
                        }
                    });
                }""", "div.x1yvgwvq" if '/reel/' in url else "article")
            except: pass

            # Extended wait for stabilization and re-render
            await asyncio.sleep(4)

            # ---------------------------------------------------------
            # STEP 1: CAPTURE SCREENSHOT
            # ---------------------------------------------------------
            captured = False
            try:
                # Target the specific container if possible
                target = article
                if '/reel/' in url:
                    reel_container = page.locator("div.x1yvgwvq").first
                    if await reel_container.count() > 0:
                        target = reel_container

                box = await target.bounding_box()
                if box:
                    print(f"📸 Element found at {box}. Taking clipped screenshot...")
                    # For wide post boxes, narrow down to article if appropriate
                    if not '/reel/' in url and box['width'] > 1200:
                         article_el = page.locator("article").first
                         if await article_el.count() > 0:
                              new_box = await article_el.bounding_box()
                              if new_box: box = new_box

                    # Avoid tiny boxes
                    if box['width'] < 100 or box['height'] < 100:
                         await target.screenshot(path=image_path, timeout=15000)
                    else:
                         await page.screenshot(path=image_path, clip=box, timeout=25000)
                    captured = True
                    print(f"✅ Screenshot saved.")
                else:
                    await target.screenshot(path=image_path, timeout=15000)
                    captured = True
                    print(f"✅ Element screenshot saved.")

            except Exception as e:
                print(f"⚠️ Screenshot failed: {e}. Trying full page screenshot...")
                try:
                    await page.screenshot(path=image_path)
                    captured = True
                except: pass

            # ---------------------------------------------------------
            # STEP 2: TEXT EXTRACTION
            # ---------------------------------------------------------
            print(f"📝 Starting text extraction...")
            text_content = ""
            
            # Strategy 1: Article H1 (usually contains the caption)
            try:
                caption_el = article.locator("h1").first
                if await caption_el.count() > 0:
                    text_content = await caption_el.inner_text()
                    print("📄 Found caption in H1")
            except: pass

            if not text_content:
                # Strategy 2: Meta description fallback (very common/reliable)
                try:
                    meta = await page.get_attribute("meta[name='description']", "content")
                    if meta:
                        text_content = meta
                        print("📄 Found caption in meta description")
                except: pass

            # Extract Username for fallback
            username = "Midia Social"
            try:
                title_meta = await page.get_attribute("meta[property='og:title']", "content")
                if title_meta:
                    if "(" in title_meta and ")" in title_meta:
                        username = title_meta.split("(")[1].split(")")[0]
                    else:
                        username = title_meta.split("•")[0].strip()
            except: pass

            # Extract Date
            post_date = None
            try:
                time_el = article.locator("time").first
                if await time_el.count() > 0:
                    post_date = await time_el.get_attribute("datetime")
            except: pass

            # Final Fallback for text
            if not text_content:
                text_content = username if username != "Midia Social" else "Midia Social Capture"

            # ---------------------------------------------------------
            # CLEANING & NORMALIZATION
            # ---------------------------------------------------------
            import re
            def cleanup_text(text):
                # Normalize Unicode (convert stylized fonts to plain text)
                text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
                # Remove non-ASCII punctuation/emojis but keep basic chars
                return re.sub(r'[^\w\s,!.?@#&"\'()-]|_', '', text).strip()
            
            if text_content:
                text_content = cleanup_text(text_content)
            
            if not text_content:
                 text_content = username

            print(f"📝 Final Title: {text_content[:50]}...")

            # ---------------------------------------------------------
            # STEP 3: DOWNLOAD FALLBACK (If capture failed or too small)
            # ---------------------------------------------------------
            if not captured or (os.path.exists(image_path) and os.path.getsize(image_path) < 3000):
                print("⚠️ Screenshot missing or too small, trying direct download...")
                try:
                    cover_url = await page.evaluate("""() => {
                        const article = document.querySelector('article') || document;
                        const imgs = Array.from(article.querySelectorAll('img'));
                        const best = imgs.find(img => img.width > 200 && img.src && (img.src.includes('fbcdn') || img.src.includes('instagram')));
                        if (best) return best.src;
                        const video = article.querySelector('video');
                        if (video && video.poster) return video.poster;
                        const meta = document.querySelector('meta[property="og:image"]');
                        return meta ? meta.content : null;
                    }""")
                    
                    if cover_url:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(cover_url) as resp:
                                if resp.status == 200:
                                    with open(image_path, 'wb') as f:
                                        f.write(await resp.read())
                                    print("✅ Downloaded cover image as fallback.")
                                    captured = True
                except: pass

            if not os.path.exists(image_path):
                return {"status": "error", "error": "Image capture failed (no file created)"}

            # Save results
            with open(text_path, "w", encoding="utf-8-sig") as f:
                f.write(text_content)
            
            return {
                "text_content": text_content,
                "image_path": image_path,
                "text_path": text_path,
                "pub_date": post_date,
                "status": "success"
            }
            
        except Exception as e:
            print(f"❌ Error scraping post: {e}")
            try:
                title = await page.title()
                if "não está disponível" in title: return {"status": "not_found", "error": "Content unavailable"}
            except: pass
            return {"status": "error", "error": str(e)}
        finally:
            await context.close()
