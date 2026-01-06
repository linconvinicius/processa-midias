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
                await page.wait_for_selector("main[role='main'], article, div.x1yvgwvq", timeout=15000)
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
            
            # Trigger lazy loading
            try:
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(0.5)
                await page.mouse.wheel(0, -500)
                await asyncio.sleep(0.8)
                # Wait for images to be visible
                await page.wait_for_selector("main img, .x1yvgwvq img, article img", timeout=10000)
            except:
                pass

            # SELECTIVE UI CLEANUP (Preserving Sidebar/Layout)
            try:
                await asyncio.sleep(1)
                await page.evaluate("""() => {
                    // We only hide intrusive popups/modals, NOT the app navigation
                    const selectors = [
                        'div[role="dialog"]', 
                        'div.x1cy8zhl.x9f619.x78zum5.x1iyjqo2.x1n2onr6', // Login wall
                        'div[style*="opacity: 0.5"]', // Overlay shadows
                        'div[style*="background-color: rgba(0, 0, 0, 0.5)"]',
                        'div._a9--._a9_0', // "Continue as" banner
                        'div.x1qjc9as' // Cookie banner or similar overlays
                    ];
                    
                    selectors.forEach(s => {
                        document.querySelectorAll(s).forEach(el => {
                            // Don't hide the main content
                            if (el.contains(document.querySelector('article')) || 
                                el.contains(document.querySelector('main'))) return;
                                
                            el.style.display = 'none';
                            el.style.visibility = 'hidden';
                        });
                    });

                    // Remove blur filters
                    document.querySelectorAll('*').forEach(el => {
                        if (el.style.filter && el.style.filter.includes('blur')) {
                            el.style.filter = 'none';
                        }
                    });

                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                }""")
            except Exception as e:
                print(f"⚠️ Cleanup failed: {e}")
                pass

            captured = False
            # Check if this is a Reel/Video post
            is_video = '/reel/' in url or (await article.locator("video").count() > 0 if '?img_index=' not in url else False)
            
            try:
                # Scroll article into view clearly and wait for it to be stable
                await article.scroll_into_view_if_needed()
                await asyncio.sleep(1)

                # Get the bounding box of the article to clip the page screenshot
                # This is more robust than article.screenshot() which often timeouts
                box = await article.bounding_box()
                
                if box:
                    print(f"📸 Article found at {box}. Taking clipped screenshot...")
                    # Clip with a bit of margin if needed, but box should be enough
                    await page.screenshot(path=image_path, clip=box, timeout=15000)
                    captured = True
                    print(f"✅ Clipped page screenshot saved.")
                else:
                    # Fallback to standard capture if box fails
                    if is_video:
                        print("🎬 Reel/Video detected")
                        target = page.locator("div.x1yvgwvq").first if '/reel/' in url else article
                        if await target.count() == 0: target = article
                        await target.screenshot(path=image_path, timeout=10000)
                    else:
                        await article.screenshot(path=image_path, timeout=10000)
                    captured = True
                    print(f"✅ Element screenshot saved.")

            except Exception as e:
                print(f"⚠️ Screenshot failed: {e}. Trying full page screenshot as fallback...")
                try:
                    await page.screenshot(path=image_path)
                    captured = True
                    print(f"✅ Full page screenshot saved as fallback.")
                except Exception as e2:
                    print(f"❌ Full page screenshot also failed: {e2}")

            # ---------------------------------------------------------
            # STEP 2: TEXT EXTRACTION
            # ---------------------------------------------------------
            print(f"📝 Starting text extraction...")
            text_content = ""
            
            # Strategy 1: Look for on-page text (usually best)
            try:
                caption_el = article.locator("h1").first
                if await caption_el.count() > 0:
                    text_content = await caption_el.inner_text()
                    print(f"📄 Found caption in H1")
            except:
                pass

            # Strategy 2: Fallback to Meta Description
            if not text_content:
                try:
                    description_meta = await page.locator("meta[property='og:description']").get_attribute("content")
                    if description_meta:
                        print(f"⚠️ H1 missing. Using meta description...")
                        if ': "' in description_meta:
                            text_content = description_meta.split(': "', 1)[1].rstrip('"')
                        else:
                            text_content = description_meta
                except:
                    pass
            
            # Extract Username for fallback
            username = "Midia Social"
            try:
                username_meta = await page.locator("meta[property='og:title']").get_attribute("content")
                if username_meta:
                    if "(" in username_meta and ")" in username_meta:
                        username = username_meta.split("(")[1].split(")")[0]
                    else:
                        username = username_meta.split("•")[0].strip()
            except:
                pass

            # Extract Date (<time>)
            post_date = None
            try:
                time_el = article.locator("time").first
                if await time_el.count() > 0:
                    post_date = await time_el.get_attribute("datetime")
            except:
                pass

            # Final Fallback for text
            if not text_content:
                text_content = username if username != "Midia Social" else "Midia Social Capture"

            # ---------------------------------------------------------
            # CLEANING RULES (Emoji Logic)
            # ---------------------------------------------------------
            import re
            def remove_emojis(text):
                return re.sub(r'[^\w\s,!.?@#&"\'()-]|_', '', text).strip()
            
            def is_only_emojis(text):
                cleaned = remove_emojis(text)
                return len(cleaned) == 0 and len(text) > 0

            if text_content:
                # Normalize Unicode (converts cursive/bold math symbols to plain letters)
                text_content = unicodedata.normalize('NFKD', text_content).encode('ascii', 'ignore').decode('ascii')
                
                if is_only_emojis(text_content):
                    text_content = username
                else:
                    cleaned_text = remove_emojis(text_content)
                    if len(cleaned_text) < len(text_content):
                        text_content = cleaned_text
            
            if not text_content.strip():
                 text_content = username

            print(f"📝 Final Title: {text_content[:50]}...")

            # ---------------------------------------------------------
            # STEP 3: FALLBACK CAPTURE (If needed)
            # ---------------------------------------------------------
            if not captured or (os.path.exists(image_path) and os.path.getsize(image_path) < 15000):
                print(f"⚠️ Screenshot missing or too small ({os.path.getsize(image_path) if os.path.exists(image_path) else 'N/A'} bytes), trying download method...")
                try:
                    cover_url = await page.evaluate("""() => {
                        const article = document.querySelector('article') || document;
                        const imgs = Array.from(article.querySelectorAll('img'));
                        for (let img of imgs) {
                            if (img.src && (img.src.includes('fbcdn') || img.src.includes('instagram')) && img.width > 200) return img.src;
                        }
                        const video = article.querySelector('video');
                        if (video && video.poster) return video.poster;
                        // Try meta as ultimate fallback
                        const ogImage = document.querySelector('meta[property="og:image"]');
                        if (ogImage) return ogImage.content;
                        return null;
                    }""")
                    
                    if cover_url:
                        print(f"📥 Attempting to download fallback image: {cover_url[:60]}...")
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(cover_url) as resp:
                                if resp.status == 200:
                                    with open(image_path, 'wb') as f:
                                        f.write(await resp.read())
                                    print(f"✅ Downloaded cover image as fallback.")
                                    captured = True
                                else:
                                    print(f"❌ Fallback download failed with status {resp.status}")
                    else:
                        print("❌ Could not find cover URL for fallback.")
                except Exception as e:
                    print(f"❌ Download fallback failed: {e}")

            # FINAL CHECK: Did we actually get a file?
            if not os.path.exists(image_path):
                print(f"❌ CRITICAL: No image file created at {image_path}")
                return {"status": "error", "error": "Image capture failed (no file created)"}

            # Save text content with BOM to help C# detection
            with open(text_path, "w", encoding="utf-8-sig") as f:
                f.write(text_content)


            # Legacy Adapter call removed. Orchestration is now handled by ProcessingService.
            
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
                is_exists = await page.title()
                if "não está disponível" in is_exists:
                     return {"status": "not_found", "error": "Content unavailable"}
            except:
                pass
            
            # await page.screenshot(path="error_instagram.png")
            return {"status": "error", "error": str(e)}
        finally:
            await context.close()
