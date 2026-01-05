
import asyncio
import os
import re
from playwright.async_api import Page, TimeoutError
from src.scraper.core.browser import BrowserManager
from src.legacy_adapter.run_adapter import run_legacy_adapter
from src.database.connection import get_settings
from datetime import datetime

class FacebookSpider:
    def __init__(self, manager: BrowserManager):
        self.manager = manager
        self.settings = get_settings()
        self.state_file = "facebook_state.json"

    async def ensure_login(self, page: Page):
        """Logs into Facebook if not already logged in."""
        try:
            print("🔵 Checking Facebook Login Status...")
            await page.goto("https://www.facebook.com/", timeout=60000, wait_until="load")
            
            # Wait for either a logged-in indicator OR the login form
            # Banner/FB Logo/Search = Logged in
            # input[name='email'] = Not logged in
            try:
                indicator = await page.wait_for_selector(
                    "div[role='banner'], svg[aria-label='Facebook'], input[type='search'], input[name='email']", 
                    timeout=20000
                )
                
                # Check what we found
                if await page.locator("input[name='email']").count() > 0:
                    print("🔄 Not logged in. Starting login flow...")
                else:
                    print("✅ Already logged in to Facebook.")
                    return
            except TimeoutError:
                print("⚠️ Could not determine login status (Timeout). Proceeding with caution...")
                # If we can't find anything, we'll try to look for the email field anyway 
                # but we won't delete the session file if it fails.

            # Username / Login Flow
            try:
                email_field = await page.wait_for_selector("input[name='email']", state="visible", timeout=10000)
                await email_field.fill(self.settings.FACEBOOK_USER)
                await asyncio.sleep(1)
                
                pass_field = await page.wait_for_selector("input[name='pass']", state="visible")
                await pass_field.fill(self.settings.FACEBOOK_PASS)
                await asyncio.sleep(1)
                
                await page.click("button[name='login']")
                
                # Wait for login success
                await page.wait_for_load_state("networkidle")
                await page.wait_for_selector("div[role='banner'], svg[aria-label='Facebook']", timeout=20000)
                
                print("✅ Login successful.")
                await page.context.storage_state(path=self.state_file)
                print("💾 Session saved.")
                
            except TimeoutError:
                # If we are here, it means we either didn't find the email field (maybe already logged in?)
                # OR we filled it and the next screen didn't load.
                content = await page.content()
                if "não está disponível agora" in content or "content isn't available" in content:
                    print("❌ Facebook blocked the login or page changed.")
                    raise
                
                # If banner/logo is visible now, we are actually logged in
                if await page.locator("div[role='banner'], svg[aria-label='Facebook']").count() > 0:
                    print("✅ Verified: Already logged in.")
                    return
                else:
                    print("❌ Login flow failed or took too long.")
                    raise

        except Exception as e:
            print(f"❌ Facebook Login Error: {e}")
            # Permanent Fix: NEVER delete the state file automatically. 
            # If it's invalid, let the user decide when to re-run manual login.
            await page.screenshot(path="error_facebook_login.png")
            raise

    async def scrape_post(self, link_data: dict):
        """Navigates to a Facebook post and captures it."""
        url = link_data.get('url')
        link_id = link_data.get('link_id', 'unknown')
        
        if not url:
             return {"status": "error", "error": "No URL provided"}

        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()
        
        try:
            await self.ensure_login(page)
            
            print(f"🔗 Navigating to {url}...")
            await page.goto(url, timeout=60000, wait_until="load")
            await page.wait_for_load_state("networkidle")
            
            # Handling "Content Not Available"
            # Text: "This content isn't available right now" or "Este conteúdo não está disponível agora"
            content = await page.content()
            if "não está disponível agora" in content or "content isn't available" in content:
                print("⚠️ Post not found or unavailable.")
                return {"status": "not_found", "error": "Content unavailable"}

            # Wait for post content
            # Priority 1: Dialog content (Modern Modal)
            # Priority 2: Generic Article
            try:
                dialog = page.locator("div[role='dialog']").first
                if await dialog.count() > 0:
                    print("🔵 Detected Dialog/Modal view.")
                    # Wait for message in dialog
                    await page.wait_for_selector("div[role='dialog'] [data-ad-preview='message'], div[role='dialog'] [data-ad-rendering-role='story_message']", timeout=10000)
                    article = dialog
                else:
                    await page.wait_for_selector("div[role='article'], div[role='main']", timeout=15000)
                    article = page.locator("div[role='article']").first
                
                # Expand "See more" if present (common in FB)
                try:
                    expand_btn = page.locator("div[role='button']", has_text=re.compile(r"Ver mais|See more", re.IGNORECASE)).first
                    if await expand_btn.count() > 0:
                        await expand_btn.click(timeout=2000)
                        await asyncio.sleep(1)
                except:
                    pass

            except TimeoutError:
                print("⚠️ Timeout waiting for post content.")
            
            # Extract Text
            text_content = ""
            article = page.locator("div[role='article']").first
            
            try:
                # Targeted selectors for modern Facebook layout
                # 'data-ad-comet-preview' is the most current identifier for post text
                post_text_selectors = [
                    "[data-ad-preview='message']",
                    "[data-ad-comet-preview='message']",
                    "[data-ad-rendering-role='story_message']",
                    "div[dir='auto']", 
                ]
                
                # Check dialog first for scoping
                is_dialog = await page.locator("div[role='dialog']").count() > 0
                search_root = page.locator("div[role='dialog']").first if is_dialog else article

                for selector in post_text_selectors:
                    elements = search_root.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        el = elements.nth(i)
                        t = await el.inner_text()
                        if t and len(t) > 5:
                            # Skip if it's just interaction counts or menu items
                            lower_t = t.lower()
                            if any(stop in lower_t for stop in ['curtir', 'comentar', 'página', 'publicidade']):
                                continue
                            
                            text_content = t
                            print(f"📄 Found post text via {selector}: {text_content[:50]}...")
                            break
                    if text_content:
                        break
            except Exception as msg_error:
                print(f"⚠️ Error in primary text extraction: {msg_error}")

            if not text_content:
                try:
                    if await article.count() > 0:
                        full_text = await article.inner_text()
                    else:
                        full_text = await page.inner_text("body")
                    
                    lines = full_text.split('\n')
                    cleaned_lines = []
                    for line in lines:
                        line = line.strip()
                        if line and len(line) > 3 and not any(word in line.lower() for word in ['curtir', 'comentar', 'compartilhar', 'like', 'comment', 'share', 'seguir', 'follow']):
                            cleaned_lines.append(line)
                    text_content = '\n'.join(cleaned_lines[:10])
                    print(f"⚠️ Using cleaned fallback text: {text_content[:50]}...")
                except:
                    pass
            
            # Fallback if specific selectors fail
            if not text_content:
                try:
                    # Get all text from article and filter out common headers/footers
                    full_article_text = await article.inner_text()
                    lines = [l.strip() for l in full_article_text.split('\n') if l.strip()]
                    # Usually the largest block after the first few metadata lines is the content
                    potential_lines = [l for l in lines if len(l) > 20 and not any(x in l.lower() for x in ['curtir', 'comentar', 'visualizações'])]
                    if potential_lines:
                        text_content = potential_lines[0]
                        print(f"📄 Found fallback text: {text_content[:50]}...")
                except:
                    pass

            if not text_content:
                text_content = "Facebook Post Capture"

            # Clean extraction for Metadata-heavy results
            if text_content and text_content != "Facebook Post Capture":
                # Remove artifacts like "Sugerido para você", "Patrocinado", etc.
                cleanup_patterns = [
                    r"^Post de .*$", 
                    r"^Sugerido para você.*$", 
                    r"^Patrocinado.*$",
                ]
                for pattern in cleanup_patterns:
                    text_content = re.sub(pattern, "", text_content, flags=re.MULTILINE | re.IGNORECASE).strip()

            # Screenshot Strategy - Improve quality by hiding modal UI
            screenshot_path = f"captures/facebook_{link_id}.png"
            os.makedirs("captures", exist_ok=True)
            
            # Hide Modal Header and X Button but KEEP the Post Header (Name/Date)
            try:
                await page.evaluate("""() => {
                    const selectorsToHide = [
                        "div[aria-label='Fechar']", 
                        "div[aria-label='Close']",
                        "div[role='dialog'] > div > div > div:first-child", # Main modal header
                        "div[role='banner']",
                        "div#header_container"
                    ];
                    selectorsToHide.forEach(s => {
                        const els = document.querySelectorAll(s);
                        els.forEach(el => { if(el) el.style.visibility = 'hidden'; });
                    });
                }""")
            except:
                pass

            is_video = False
            try:
                # Check for video players
                video_elements = await page.locator("video").count()
                if video_elements > 0:
                    is_video = True
                    print("🎬 Detected video post")
            except:
                pass
            
            if is_video:
                try:
                    video = page.locator("video").first
                    poster_url = await video.get_attribute("poster")
                    
                    if poster_url:
                        print(f"🖼️ Found video poster, downloading thumbnail...")
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(poster_url) as resp:
                                if resp.status == 200:
                                    with open(screenshot_path, 'wb') as f:
                                        f.write(await resp.read())
                                    print(f"✅ Saved video thumbnail: {screenshot_path}")
                                else:
                                    raise Exception("Failed to download poster")
                    else:
                        print(f"⚠️ No poster found, taking screenshot of video player...")
                        if await article.count() > 0:
                            await article.screenshot(path=screenshot_path)
                        else:
                            await page.screenshot(path=screenshot_path)
                except Exception as thumb_error:
                    print(f"⚠️ Could not extract thumbnail ({thumb_error}), using screenshot fallback")
                    if await article.count() > 0:
                        await article.screenshot(path=screenshot_path)
                    else:
                        await page.screenshot(path=screenshot_path)
            else:
                # Optimal visual capture: find the container that holds the post within the modal
                try:
                    # Priority 1: Dialog content (captures everything focused)
                    dialog = page.locator("div[role='dialog']").first
                    if await dialog.count() > 0:
                        print("📸 Capturing full dialog content...")
                        # Hide elements like "Close" or background headers to clean up
                        await page.evaluate("""() => {
                            const toHide = ["div[aria-label='Fechar']", "div[aria-label='Close']", "div[role='banner']"];
                            toHide.forEach(s => {
                                const el = document.querySelector(s);
                                if(el) el.style.display = 'none';
                            });
                        }""")
                        
                        # Use the actual post container inside the dialog if possible
                        # Based on research: the second child of the scrollable area is usually the post
                        scrollable = dialog.locator("[scrollable='true'], .xy5w88m").first
                        if await scrollable.count() > 0:
                            post_area = scrollable.locator("> div:nth-child(2)").first
                            if await post_area.count() > 0:
                                await post_area.screenshot(path=screenshot_path)
                                print("📸 Captured specific post area in dialog.")
                            else:
                                await scrollable.screenshot(path=screenshot_path)
                                print("📸 Captured full scrollable area in dialog.")
                        else:
                            await dialog.screenshot(path=screenshot_path)
                            print("📸 Captured generic dialog container.")
                    
                    elif await article.count() > 0:
                        print("📸 Capturing standard article...")
                        await article.screenshot(path=screenshot_path)
                    else:
                        print("📸 Capturing full page (fallback)...")
                        await page.screenshot(path=screenshot_path)
                except Exception as ss_error:
                    print(f"⚠️ Screenshot error: {ss_error}")
                    await page.screenshot(path=screenshot_path)
                
                print(f"✅ Saved screenshot: {screenshot_path}")

            # Save Text File
            text_path = f"captures/facebook_{link_id}.txt"
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(text_content)

            # DEFER ADAPTER CALL TO PROCESSING SERVICE (Consistency)
            return {
                "text_content": text_content,
                "image_path": screenshot_path,
                "text_path": text_path,
                "status": "success"
            }
        except Exception as e:
            print(f"❌ Error scraping Facebook: {e}")
            await page.screenshot(path=f"error_facebook_{link_id}.png")
            return {"status": "error", "error": str(e)}
        finally:
            await context.close()