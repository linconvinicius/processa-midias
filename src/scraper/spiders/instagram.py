import asyncio
import os
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
        """Gerencia o login no Instagram usando o estado salvo."""
        try:
            await page.goto("https://www.instagram.com/" )
            try:
                # Verifica se já está logado (ícone de pesquisa ou perfil)
                await page.wait_for_selector("svg[aria-label='Pesquisa'], svg[aria-label='Search']", timeout=8000)
                return
            except TimeoutError:
                print("🔄 Sessão não encontrada. Iniciando fluxo de login...")

            await page.wait_for_selector("input[name='username']", timeout=10000)
            await page.fill("input[name='username']", self.settings.INSTAGRAM_USER)
            await page.fill("input[name='password']", self.settings.INSTAGRAM_PASS)
            await page.click("button[type='submit']")
            
            # Aguarda confirmação de login
            await page.wait_for_selector("svg[aria-label='Pesquisa'], svg[aria-label='Search']", timeout=15000)
            await page.context.storage_state(path=self.state_file)
            print("✅ Login realizado com sucesso e sessão salva.")
        except Exception as e:
            print(f"❌ Falha crítica no login: {e}")
            raise

    async def scrape_post(self, link_data: dict):
        """
        Fluxo principal de captura com conversão de layout e extração resiliente de legenda.
        """
        raw_url = link_data.get('url')
        link_id = link_data.get('link_id', 'unknown')
        
        # Caminhos de saída (conforme esperado pelo SocialMediaProcessor)
        image_path = f"captures/instagram_{link_id}.png"
        text_path = f"captures/instagram_{link_id}.txt"
        os.makedirs("captures", exist_ok=True)

        # ============================================================
        # TRUQUE DE LAYOUT: Converte Reel para Post (/p/)
        # Isso força o layout estável (Vídeo à esquerda, Legenda à direita)
        # ============================================================
        url = raw_url.split("?")[0] if "?" in raw_url else raw_url
        if '/reel/' in url:
            url = url.replace('/reel/', '/p/')
            print(f"🔄 [Link {link_id}] Convertendo Reel para layout de Post.")

        # Cria novo contexto (com Stealth e GPU fix via BrowserManager)
        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()
        
        try:
            await self.ensure_login(page)
            
            print(f"🔗 [Link {link_id}] Acessando: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 1. Tenta usar o helper especializado (Captura Relâmpago / Híbrida)
            captured = await handle_reel_capture(page, url, image_path)
            
            if not captured:
                print(f"📸 [Link {link_id}] Helper falhou, tentando captura de article padrão...")
                article = await page.wait_for_selector("article", timeout=20000)
                
                # Limpeza visual rápida
                await page.evaluate("""() => {
                    document.querySelectorAll('nav, header, [role="banner"]').forEach(el => el.style.display = 'none');
                    document.body.style.backgroundColor = 'white';
                }""")
                
                await article.screenshot(path=image_path)
                captured = True

            # ============================================================
            # EXTRAÇÃO DE TEXTO (Legenda) - Versão Ultra Resiliente
            # ============================================================
            print(f"📝 [Link {link_id}] Extraindo legenda...")
            caption = ""
            
            # Lista de seletores conhecidos (do mais comum ao mais raro)
            caption_selectors = [
                "article h1",                      # Layout padrão de post
                "div._ap30",                       # Seletor comum em posts novos
                "span._ap30",                      # Variação de span
                "article span[dir='auto']"         # Seletor genérico de texto de post
            ]
            
            for selector in caption_selectors:
                try:
                    # Tenta encontrar o texto dentro do article para não pegar comentários
                    element = page.locator(f"article {selector}").first
                    if await element.count() > 0:
                        text = await element.inner_text(timeout=3000)
                        if text and len(text) > 2:
                            caption = text
                            print(f"✅ Legenda encontrada via: {selector}")
                            break
                except:
                    continue

            # Fallback final via Meta Tags (se a interface falhar)
            if not caption:
                try:
                    meta_caption = await page.locator("meta[property='og:description']").get_attribute("content", timeout=2000)
                    if meta_caption:
                        if ":" in meta_caption:
                            caption = meta_caption.split(":", 1)[-1].strip()
                        else:
                            caption = meta_caption
                        print("✅ Legenda extraída via Meta Tag.")
                except:
                    pass

            # Salva o arquivo de texto
            final_text = caption if caption else "Legenda não encontrada."
            with open(text_path, "w", encoding="utf-8-sig") as f:
                f.write(final_text)

            return {
                "status": "success",
                "image_path": image_path,
                "text_path": text_path,
                "link_id": link_id
            }

        except Exception as e:
            print(f"❌ Erro ao processar Link {link_id}: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await page.close()
