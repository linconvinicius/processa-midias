import asyncio
import os
import unicodedata
import re
from playwright.async_api import Page, TimeoutError
from src.scraper.core.browser import BrowserManager
from src.database.connection import get_settings
from src.scraper.instagram_reels_helper import handle_reel_capture

class InstagramSpider:
    def __init__(self, manager: BrowserManager):
        self.manager = manager
        self.settings = get_settings()
        self.state_file = "instagram_state.json"

    async def ensure_login(self, page: Page):
        """Gerencia o login no Instagram."""
        try:
            await page.goto("https://www.instagram.com/" )
            if await page.locator("svg[aria-label='Pesquisa'], svg[aria-label='Search']").count() > 0:
                return
            await page.fill("input[name='username']", self.settings.INSTAGRAM_USER)
            await page.fill("input[name='password']", self.settings.INSTAGRAM_PASS)
            await page.click("button[type='submit']")
            await page.wait_for_selector("svg[aria-label='Pesquisa']", timeout=15000)
            await page.context.storage_state(path=self.state_file)
        except: pass

    async def scrape_post(self, link_data: dict):
        """Captura posts com substituição inteligente de legendas compostas apenas por emojis."""
        raw_url = link_data.get('url')
        link_id = link_data.get('link_id', 'unknown')
        image_path = f"captures/instagram_{link_id}.png"
        text_path = f"captures/instagram_{link_id}.txt"
        os.makedirs("captures", exist_ok=True)

        url = raw_url.split("?")[0] if "?" in raw_url else raw_url
        if '/reel/' in url: url = url.replace('/reel/', '/p/')

        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()
        
        try:
            await self.ensure_login(page)
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Captura de Imagem/Vídeo
            await handle_reel_capture(page, url, image_path)

            # 2. Extração de Metadados (@Usuário e Localização)
            username = ""
            location = ""
            try:
                user_el = page.locator("header a[role='link']").first
                if await user_el.count() > 0:
                    username = await user_el.inner_text()
                
                loc_el = page.locator("header a[href*='/explore/locations/']").first
                if await loc_el.count() > 0:
                    location = await loc_el.inner_text()
            except: pass

            # 3. Extração de Legenda
            caption = ""
            try:
                element = page.locator("article h1, article span._ap30").first
                caption = await element.inner_text(timeout=5000)
            except:
                try:
                    meta_content = await page.locator('meta[property="og:description"]').get_attribute("content", timeout=3000)
                    if meta_content and ":" in meta_content:
                        caption = meta_content.split(":", 1)[-1].strip()
                except: caption = ""

            # 4. LÓGICA INTELIGENTE: Detectar se a legenda é apenas Emojis
            original_caption = caption.strip()
            
            # Remove emojis para testar se sobra algum texto alfanumérico
            # Esta regex remove a maioria dos emojis e símbolos Unicode
            text_only = re.sub(r'[^\w\s,.;:!?()\-]', '', original_caption).strip()
            
            # Se após remover emojis não sobrar texto real OU a legenda for vazia
            if not text_only or len(text_only) < 2:
                print(f"✨ Legenda detectada como 'Apenas Emojis' ou Vazia. Adicionando metadados...")
                meta_parts = []
                if username: meta_parts.append(f"Post de @{username}")
                if location: meta_parts.append(f"em {location}")
                
                prefix = " | ".join(meta_parts)
                # Mantém os emojis originais após o prefixo (o banco limpará os emojis depois)
                final_text = f"{prefix}\n{original_caption}".strip()
            else:
                # Legenda tem texto real, mantemos apenas ela
                final_text = original_caption

            # 5. LIMPEZA FINAL PARA O BANCO (Remove o que viraria ????)
            if final_text:
                final_text = unicodedata.normalize('NFKD', final_text)
                final_text = final_text.encode('ascii', 'ignore').decode('ascii')
                final_text = " ".join(final_text.split())

            # 6. Salvamento
            with open(text_path, "w", encoding="utf-8") as f:
                f.write(final_text if final_text else "Legenda nao encontrada.")

            return {
                "status": "success",
                "image_path": image_path,
                "text_path": text_path,
                "link_id": link_id
            }

        except Exception as e:
            print(f"❌ Erro no Instagram {link_id}: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await page.close()
