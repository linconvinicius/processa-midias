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
        """Garante que o usuário está logado no Twitter/X."""
        try:
            # Verifica se já está logado por elementos da UI
            if await page.locator("[data-testid='SideNav_AccountSwitcher_Button']").count() > 0:
                return

            print("🔵 Verificando status de login no Twitter...")
            await page.goto("https://x.com/home", timeout=60000, wait_until='domcontentloaded' )
            
            if await page.locator("[data-testid='SideNav_AccountSwitcher_Button']").count() > 0:
                print("✅ Sessão ativa via cookies.")
                return

            print("🔑 Sessão expirada. Iniciando fluxo de login...")
            await page.goto("https://x.com/login", timeout=60000 )

            # Usuário
            username_input = await page.wait_for_selector("input[autocomplete='username'], input[name='text']", timeout=10000)
            await username_input.fill(self.settings.TWITTER_USER)
            await page.click("button:has-text('Próximo'), button:has-text('Next')")

            # Senha
            await asyncio.sleep(2)
            password_input = await page.wait_for_selector("input[name='password'], input[type='password']", timeout=15000)
            await password_input.fill(self.settings.TWITTER_PASS)

            # Botão Entrar
            await asyncio.sleep(1)
            await page.click("button[data-testid='LoginForm_Login_Button'], button:has-text('Log in'), button:has-text('Entrar')")

            await page.wait_for_selector("[data-testid='SideNav_AccountSwitcher_Button']", timeout=20000)
            print("✅ Login realizado com sucesso.")

            # Salva o estado da sessão
            await page.context.storage_state(path=self.state_file)
        except Exception as e:
            print(f"❌ Falha no login do Twitter: {e}")
            raise

    async def scrape_post(self, link_data: dict):
        """Navega até um tweet e realiza a captura."""
        url = link_data.get('url')
        link_id = link_data.get('link_id', 'unknown')
        
        if not url:
             return {"status": "error", "error": "No URL provided"}

        # Usa o contexto robusto do BrowserManager
        context = await self.manager.new_context(storage_state=self.state_file)
        page = await context.new_page()

        try:
            # Normaliza a URL para x.com
            url = url.replace("twitter.com", "x.com").replace("http://", "https://" )
            
            print(f"🔗 [Link {link_id}] Acessando: {url}")
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            
            # Verifica se foi redirecionado para login
            if "x.com/login" in page.url or await page.locator("[data-testid='loginButton']").count() > 0:
                print("🔑 Redirecionado para login. Autenticando...")
                await self.ensure_login(page)
                await page.goto(url, timeout=90000, wait_until="networkidle")

            # --- CORREÇÃO DOS SELETORES DE ERRO ---
            # Usamos a sintaxe :has-text() que é a correta para o Playwright
            error_patterns = [
                ":has-text(\"Hmm...this page doesn't exist\")",
                ":has-text(\"Página não encontrada\")",
                ":has-text(\"Ih, esta página não existe\")",
                ":has-text(\"Esta conta não existe\")",
                ":has-text(\"This account doesn't exist\")"
            ]
            
            # Espera pelo Tweet OU por uma mensagem de erro (sem quebrar o seletor)
            try:
                # Combinamos apenas seletores CSS válidos
                await page.wait_for_selector("[data-testid='tweetText'], [data-testid='error-detail']", timeout=20000)
            except TimeoutError:
                print("⚠️ Timeout aguardando tweet. Verificando se a página existe...")

            # Verifica se alguma mensagem de erro está visível
            for pattern in error_patterns:
                if await page.locator(pattern).count() > 0:
                    print(f"⚠️ Erro do Twitter detectado: {pattern}")
                    return {"status": "not_found", "error": "Tweet or account not found (404)"}

            # Extração de conteúdo
            tweet_locator = page.locator("[data-testid='tweetText']").first
            tweet_text = await tweet_locator.inner_text() if await tweet_locator.count() > 0 else ""
            
            # Normalização de texto
            if tweet_text:
                tweet_text = unicodedata.normalize('NFKD', tweet_text).encode('ascii', 'ignore').decode('ascii')

            # Caminhos de saída
            image_path = f"captures/twitter_{link_id}.png"
            text_path = f"captures/twitter_{link_id}.txt"
            os.makedirs("captures", exist_ok=True)
            
            # Screenshot do tweet (tentamos focar no elemento do tweet para um print melhor)
            tweet_article = page.locator("article[data-testid='tweet']").first
            if await tweet_article.count() > 0:
                await tweet_article.screenshot(path=image_path)
            else:
                await page.screenshot(path=image_path)
            
            with open(text_path, "w", encoding="utf-8-sig") as f:
                f.write(tweet_text)

            return {
                "status": "success",
                "image_path": image_path,
                "text_path": text_path,
                "text_content": tweet_text
            }

        except Exception as e:
            print(f"❌ Erro ao processar tweet {link_id}: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await page.close()
