import asyncio
import os
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
        
        try:
            await self.ensure_login(page)
            
            print(f"🔗 Navigating to {url}...")
            
            # Clean URL to avoid direct deep linking issues (like img_index)
            if "?" in url:
                clean_url = url.split("?")[0]
                print(f"🧹 Cleaned URL: {clean_url} (removed params)")
                await page.goto(clean_url)
            else:
                await page.goto(url)
            
            # Wait for content (Article or Image or Main)
            try:
                # Instagram posts are usually wrapped in an article or have a main role
                # Try waiting for the main role which contains the post
                await page.wait_for_selector("main[role='main'], article", timeout=15000)
                
                # locate the container
                if await page.locator("article").count() > 0:
                    article = page.locator("article").first
                else:
                    article = page.locator("main[role='main']")
                    
            except TimeoutError:
                # Check for "Page Not Found" textual clues
                content = await page.content()
                if "Esta página não está disponível" in content or "Page Not Found" in content:
                     print("⚠️ Post deleted or not found.")
                     return {"status": "not_found", "error": "Content deleted or unavailable"}
                raise
            
            # Extract Description (Caption)
            text_content = ""
            
            # Strategy 1: Look for on-page text (usually best)
            # Instagram often uses an H1 for the first post caption in the web view.
            try:
                caption_el = article.locator("h1").first
                if await caption_el.count() > 0:
                    text_content = await caption_el.inner_text()
                    print(f"📄 Found caption in H1: {text_content[:50]}...")
            except:
                pass

            # Strategy 2: Fallback to Meta Description
            if not text_content:
                try:
                    description_meta = await page.locator("meta[property='og:description']").get_attribute("content")
                    if description_meta:
                        print(f"⚠️ H1 missing. Using meta description: {description_meta[:50]}...")
                        # Meta format: "{Stats} - {User} on {Date}: \"{Caption}\""
                        # cleaning logic: find the first ': "' and take everything after.
                        if ': "' in description_meta:
                            text_content = description_meta.split(': "', 1)[1]
                            # Remove trailing quote if present (regex or strip)
                            text_content = text_content.rstrip('"')
                            print(f"🧹 Cleaned meta caption: {text_content[:50]}...")
                        else:
                            # Fallback if format is weird
                            text_content = description_meta
                except:
                    pass
            
            # Extract Username for fallback (Rule: Emoji only -> use username)
            username = "Midia Social"
            try:
                # Try getting username from meta
                username_meta = await page.locator("meta[property='og:title']").get_attribute("content")
                if username_meta:
                    # Format: "User (@username) on Instagram..." or "Name (@username)..."
                    # We want the handle or name. Typically "Name (@handle)"
                    if "(" in username_meta and ")" in username_meta:
                        username = username_meta.split("(")[1].split(")")[0] # Get handle
                    else:
                        username = username_meta.split("•")[0].strip() # Fallback
            except:
                pass

            # Extract Date (<time>)
            post_date = None
            try:
                # Instagram uses <time datetime="..."> inside the article
                time_el = article.locator("time").first
                if await time_el.count() > 0:
                    post_date = await time_el.get_attribute("datetime")
                    print(f"📅 Found post date: {post_date}")
            except Exception as e:
                print(f"⚠️ Date extraction failed: {e}")


            # Final Fallback for text
            if not text_content:
                text_content = username if username != "Midia Social" else "Midia Social Capture"

            # ---------------------------------------------------------
            # CLEANING RULES (Emoji Logic)
            # 1. Only Emojis -> Save Username
            # 2. Text + Emojis -> Remove Emojis
            # 3. No Emojis -> Keep as is
            # ---------------------------------------------------------
            import re
            
            def remove_emojis(text):
                # Defines a broad regex for emojis
                return re.sub(r'[^\w\s,!.?@#&"\'()-]|_', '', text).strip()
            
            def is_only_emojis(text):
                cleaned = remove_emojis(text)
                return len(cleaned) == 0 and len(text) > 0

            if text_content:
                if is_only_emojis(text_content):
                    print(f"🧹 Title is only emojis. Using username: {username}")
                    text_content = username
                else:
                    # Check if it has emojis to remove
                    cleaned_text = remove_emojis(text_content)
                    if len(cleaned_text) < len(text_content):
                        print(f"🧹 Removing emojis from title...")
                        text_content = cleaned_text
            
            # Ensure not empty after cleaning
            if not text_content.strip():
                 text_content = username

            print(f"📝 Final Title: {text_content}")

            print(f"📝 Extracted text length: {len(text_content)}")
            
            # Screenshot Strategy: Handle Reels/Videos differently
            link_id = link_data.get('link_id', 'unknown')
            image_path = f"captures/instagram_{link_id}.png"
            os.makedirs("captures", exist_ok=True)
            
            # Wait specifically for media to load
            try:
                # 1. Scroll a bit to trigger lazy loading
                await page.mouse.wheel(0, 300)
                await asyncio.sleep(0.5)
                await page.mouse.wheel(0, -300)
                await asyncio.sleep(0.5)

                # 2. Wait for any image/video in article
                await page.wait_for_selector("article img, article video", timeout=8000)
                
                # 3. Hover over the main media container to force load
                try:
                    media_container = page.locator("article div._aagv, article div._akz9").first
                    if await media_container.count() > 0:
                        await media_container.hover()
                except:
                    pass
                
                # 4. Wait for network idle
                await page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass

            # Variable to track if we successfully captured an image
            captured = False

            # Check if this is a Reel/Video post
            is_video = False
            try:
                # Primary check: URL contains '/reel/' (most reliable)
                if '/reel/' in url:
                    is_video = True
                    print("🎬 Detected Reel post (URL pattern)")
                else:
                    # Secondary check: Look for video element (but only if not a carousel)
                    # Carousels have ?img_index= in URL, so we skip video detection for them
                    if '?img_index=' not in url:
                        video_elements = await article.locator("video").count()
                        if video_elements > 0:
                            is_video = True
                            print("🎬 Detected Video post (video element found)")
            except:
                pass
            
            if is_video:
                # NEW STRATEGY: Screenshot FIRST, then extract data
                # This captures the actual visual state before any DOM manipulation
                
                print("🎬 Reel/Video detected - using screenshot-first strategy")
                
                # 1. WAIT FOR FULL PAGE LOAD AND IMAGE TO APPEAR
                try:
                    # Hide problematic UI elements before screenshotting
                    await page.evaluate("""() => {
                        const toHide = [
                            '[role="dialog"]', '[role="presentation"]', '[role="navigation"]',
                            'nav', 'header', '._acum', '._acb3', '._acb6', 
                            '.x1dr59a3', 'div.x9f619.x1n2onr6.x1ja2u2z',
                            'div.x1n2onr6.x1iyjqo2[role="button"]', // Messages button
                            'div[role="button"][aria-label*="Mensagens"]',
                            'div[role="button"][aria-label*="Direct"]'
                        ];
                        toHide.forEach(s => {
                            document.querySelectorAll(s).forEach(el => {
                                el.style.display = 'none';
                                el.style.visibility = 'hidden';
                                el.style.opacity = '0';
                            });
                        });
                        // Restore overflow to ensure proper rendering
                        document.body.style.overflow = 'auto';
                        document.documentElement.style.overflow = 'auto';
                    }""")

                    # Wait for video or image to be visible
                    await page.wait_for_selector("article video, article img[src*='fbcdn']", timeout=10000)
                    print("✅ Media element found")
                    
                    # Extra wait to ensure image is fully loaded and rendered
                    await asyncio.sleep(5)
                    
                    # Wait for network to be idle
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    print("✅ Network idle")
                    
                except Exception as e:
                    print(f"⚠️ UI Cleanup or Media Wait failed: {e}, continuing anyway...")
                
                # 2. TAKE SCREENSHOT IMMEDIATELY (captures current visual state)
                print("📸 Taking screenshot of post/reel...")
                try:
                    # Try to find a clean container for the Reel
                    # Strategy: article is usually the best standard wrapper
                    target_element = article
                    
                    # If it's a Reel, we might want to capture a specific centered div if article is too wide
                    if '/reel/' in url:
                        # Common Reel container classes from subagent analysis
                        reel_container = page.locator("div.x1yvgwvq").first
                        if await reel_container.count() > 0:
                            target_element = reel_container
                            print("📸 Target element: Specific Reel container (div.x1yvgwvq)")

                    await target_element.screenshot(path=image_path)
                    print(f"✅ Screenshot saved: {image_path}")
                    captured = True
                except Exception as e:
                    print(f"❌ Screenshot failed: {e}")
                    captured = False
                
                # 3. FALLBACK: If screenshot failed, try download method
                if not captured:
                    print("⚠️ Screenshot failed, trying download method...")
                    try:
                        # Find cover image URL
                        cover_url = await page.evaluate("""() => {
                            const article = document.querySelector('article') || document;
                            const imgs = Array.from(article.querySelectorAll('img'));
                            for (let img of imgs) {
                                if (img.src && img.src.includes('fbcdn') && img.width > 200) {
                                    return img.src;
                                }
                            }
                            const video = article.querySelector('video');
                            if (video && video.poster) return video.poster;
                            return null;
                        }""")
                        
                        if cover_url:
                            print(f"📥 Downloading cover image: {cover_url[:50]}...")
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(cover_url) as resp:
                                    if resp.status == 200:
                                        with open(image_path, 'wb') as f:
                                            f.write(await resp.read())
                                        print(f"✅ Downloaded cover image: {image_path}")
                                        captured = True
                    except Exception as e:
                        print(f"❌ Download fallback also failed: {e}")
            else:
                # Not a video/Reel - Standard screenshot
                try:
                    # Hide problematic UI elements
                    await page.evaluate("""() => {
                        const toHide = ['[role="dialog"]', '[role="presentation"]', 'nav', 'header', '._acum', '._acb3', '._acb6', '.x1dr59a3'];
                        toHide.forEach(s => {
                            document.querySelectorAll(s).forEach(el => { el.style.display = 'none'; el.style.visibility = 'hidden'; });
                        });
                        document.body.style.overflow = 'auto';
                    }""")
                    await article.screenshot(path=image_path)
                    captured = True
                    print(f"📸 Saved post screenshot: {image_path}")
                except Exception as ss_error:
                    print(f"⚠️ Standard screenshot failed: {ss_error}")
                    captured = False
            # Save text content to file for adapter
            text_path = f"captures/instagram_{link_id}.txt"
            with open(text_path, "w", encoding="utf-8") as f:
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
