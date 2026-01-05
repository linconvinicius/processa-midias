import os
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from src.database.connection import get_settings

class BrowserManager:
    def __init__(self):
        self.settings = get_settings()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()

        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

    async def new_context(self, storage_state: Optional[str] = None) -> BrowserContext:
        if not self.browser:
            await self.start()

        state_path = storage_state if storage_state and os.path.exists(storage_state) else None

        return await self.browser.new_context(
            storage_state=state_path,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="pt-BR"
        )

    async def new_page(self) -> Page:
        if not self.context:
            self.context = await self.new_context()
        return await self.context.new_page()

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
