import asyncio
import os
from playwright.async_api import Page, TimeoutError
from src.scraper.core.browser import BrowserManager
from src.database.connection import get_settings

class FacebookSpider:
    def __init__(self, manager: BrowserManager):
        self.manager = manager
        self.settings = get_settings()
        self.state_file = "facebook_state.json"

    async def ensure_login(self, page: Page):
        """Garante que o usuário está logado no Facebook."""
        try:
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded" )
            if await page.locator("input[placeholder*='Pesquisar'], a[href*='/me/']").count() > 0:
                return

            print("🔑 Iniciando fluxo de login no Facebook...")
            await page.fill("input[id='email']", self.settings.FACEBOOK_USER)
            await page.fill("input[id='pass']", self.settings.FACEBOOK_PASS)
            await page.click("button[name='login']")
            
            await page.wait_for_selector("a[href*='/me/']", timeout=30000)
            await page.context.storage_state(path=self.state_file)
            print("✅ Login realizado e sessão salva.")
        except Exception as e:
            print(f"⚠️ Aviso no login do Facebook: {e}")

    async def scrape_post(self, link_data: dict):
        """Captura posts do Facebook priorizando a visualização em Modal/Dialog."""
        url = link_data.get('url')
        link_id = link_data.get('link_id', 'unknown')
        image_path = f"captures/facebook_{link_id}.png"
        text_path = f"captures/facebook_{link_id}.txt"
        os.makedirs("captures", exist_ok=True)

        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()

        try:
            print(f"🔗 [Link {link_id}] Acessando Facebook: {url}")
            # Navegação com networkidle para garantir carregamento de mídias
            await page.goto(url, wait_until="networkidle", timeout=90000)
            
            # 1. ESPERA PELO CONTEÚDO (Priorizando o Modal/Dialog)
            print("⏳ Aguardando renderização do post...")
            # O Facebook costuma abrir posts individuais em um [role='dialog']
            main_selectors = ["[role='dialog']", "div[role='main']", "article", "div[data-ad-preview='message']"]
            try:
                await page.wait_for_selector(", ".join(main_selectors), timeout=30000)
            except:
                print("⚠️ Aviso: Post demorou a aparecer visualmente.")

            # Pausa para estabilização e carregamento de frames de vídeo/imagem
            await asyncio.sleep(4)

            # 2. EXTRAÇÃO DE TEXTO (Focada no Modal para evitar pegar o fundo)
            post_text = ""
            text_selectors = [
                "[role='dialog'] [data-ad-preview='message']", 
                "[role='dialog'] div[dir='auto']",
                "div[data-ad-preview='message']",
                "div[role='article'] div[dir='auto']"
            ]
            
            for sel in text_selectors:
                locator = page.locator(sel).first
                if await locator.count() > 0:
                    post_text = await locator.inner_text()
                    if post_text and len(post_text) > 5: 
                        print(f"📝 Legenda encontrada via: {sel}")
                        break

            with open(text_path, "w", encoding="utf-8-sig") as f:
                f.write(post_text if post_text else "Legenda não encontrada.")

            # 3. SCREENSHOT DO CONTEÚDO EM DESTAQUE
            # Se houver um dialog aberto, tiramos print dele. Se não, do contêiner principal.
            is_dialog = await page.locator("[role='dialog']").count() > 0
            target_selector = "[role='dialog']" if is_dialog else "div[role='main'], article"
            target = page.locator(target_selector).first
            
            if await target.count() > 0:
                # Se for um dialog, limpamos o fundo esbranquiçado para o print ficar nítido
                if is_dialog:
                    await page.evaluate("""() => {
                        const overlays = document.querySelectorAll('div[style*="background-color: rgba(255, 255, 255"]');
                        overlays.forEach(el => el.style.backgroundColor = 'transparent');
                    }""")
                
                # Centraliza e captura
                await target.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                # Captura o elemento (Vídeo/Imagem + Legenda)
                await target.screenshot(path=image_path)
                print(f"✅ Captura realizada do contêiner: {target_selector}")
            else:
                # Fallback total
                await page.screenshot(path=image_path)

            return {
                "status": "success",
                "image_path": image_path,
                "text_path": text_path,
                "text_content": post_text
            }

        except Exception as e:
            print(f"❌ Erro ao processar Facebook {link_id}: {e}")
            await page.screenshot(path=f"captures/error_fb_{link_id}.png")
            return {"status": "error", "error": str(e)}
        finally:
            await page.close()
