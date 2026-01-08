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
            # Argumentos de inicialização focados em ocultar a automação e habilitar vídeo
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--use-gl=swiftshader",
                    "--mute-audio",
                    "--no-first-run",
                    "--no-service-autorun",
                    "--password-store=basic"
                ]
            )

    async def new_context(self, storage_state: Optional[str] = None) -> BrowserContext:
        if not self.browser:
            await self.start()

        state_path = storage_state if storage_state and os.path.exists(storage_state) else None

        # Criamos o contexto com um User-Agent real e estável
        context = await self.browser.new_context(
            storage_state=state_path,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )

        # ============================================================
        # SCRIPT DE EVASÃO "NÍVEL AGENTE" (O ESCUDO DEFINITIVO)
        # ============================================================
        await context.add_init_script("""
            // 1. Remove a propriedade navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // 2. Mascara a plataforma para parecer um Windows real
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

            // 3. Simula plugins comuns que navegadores reais possuem
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });

            // 4. Mascara a WebGL (O Instagram usa isso para detectar Headless/Servidores)
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // Mascara o Renderer e o Vendor para parecer uma placa Intel real
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                return getParameter.apply(this, arguments);
            };

            // 5. Simula o objeto window.chrome para sites que verificam sua existência
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 6. Mascara as permissões de notificação
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)
        # ============================================================

        return context

    async def new_page(self) -> Page:
        if not self.context:
            self.context = await self.new_context()
        return await self.context.new_page()

    async def close(self):
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()
