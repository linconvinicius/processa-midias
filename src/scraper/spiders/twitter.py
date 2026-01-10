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
        self.state_file = "twitter_state.json" # Manter o atributo, mas não usá-lo para login

    async def scrape_post(self, link_data: dict):
        """Navega até um tweet e realiza a captura."""
        url = link_data.get("url")
        link_id = link_data.get("link_id", "unknown")

        if not url:
            return {"status": "error", "error": "No URL provided"}

        context = await self.manager.new_context()
        page = await context.new_page()

        try:
            url = url.replace("twitter.com", "x.com").replace("http://", "https://" )
            print(f"🔗 [Link {link_id}] Acessando: {url}")
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")

            # Adiciona uma espera para a página carregar completamente
            await asyncio.sleep(5)

            # Tenta capturar o tweet principal (o de resposta)
            main_tweet_selector = "article[data-testid=\'tweet\']"
            await page.wait_for_selector(main_tweet_selector, timeout=20000)
            main_tweet = page.locator(main_tweet_selector).first

            # Captura o screenshot e o texto do tweet de resposta
            image_path = f"captures/twitter_{link_id}_reply.png"
            text_path = f"captures/twitter_{link_id}_reply.txt"
            os.makedirs("captures", exist_ok=True)

            await main_tweet.screenshot(path=image_path)
            tweet_text = await main_tweet.inner_text()

            # Normalização de texto
            if tweet_text:
                tweet_text = unicodedata.normalize("NFKD", tweet_text).encode("ascii", "ignore").decode("ascii")

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
