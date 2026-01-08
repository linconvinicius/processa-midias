import asyncio
from playwright.async_api import Page

async def handle_reel_capture(page: Page, url: str, output_path: str) -> bool:
    """
    Captura Inteligente: 
    - Para VÍDEOS: Captura instantânea (sleep 0.0) para evitar bloqueio.
    - Para IMAGENS: Aguarda carregamento completo para garantir qualidade.
    """
    try:
        print(f"🚀 [Instagram] Iniciando captura inteligente: {url}")

        # 1. Bloqueio de telemetria para ganhar tempo contra o Bot Shield
        await page.route("**/logging/*", lambda route: route.abort())
        await page.route("**/browser_metrics/*", lambda route: route.abort())

        # 2. Navegação veloz
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 3. Detecção de tipo de mídia
        # Esperamos até que um vídeo ou uma imagem de post apareça
        media_selector = "video, article img[style*='object-fit: cover'], div._aagv img"
        try:
            await page.wait_for_selector(media_selector, timeout=15000)
        except:
            print("⚠️ Mídia não detectada no tempo esperado, tentando print direto.")

        # 4. Lógica Diferenciada por Tipo de Mídia
        is_video = await page.locator("video").count() > 0
        
        if is_video:
            print("🎬 Vídeo detectado! Aplicando Captura Instantânea (Atraso Zero).")
            # Para vídeos, disparar o mais rápido possível para vencer o bloqueio
            await asyncio.sleep(0.0)
        else:
            print("📸 Imagem detectada! Aguardando carregamento completo...")
            # Para imagens, garantimos que a foto carregou 100% (sem borrão)
            # Esperamos o atributo 'complete' da imagem via JS
            await page.evaluate("""
                async () => {
                    const img = document.querySelector('article img');
                    if (img && !img.complete) {
                        await new Promise(resolve => {
                            img.onload = resolve;
                            img.onerror = resolve;
                            setTimeout(resolve, 3000); // Timeout de segurança
                        });
                    }
                }
            """)
            await asyncio.sleep(1.0) # Estabilização extra para imagens

        # 5. Screenshot do Contêiner (Vídeo/Imagem + Legenda)
        target = page.locator("article").first
        if await target.count() > 0:
            await target.screenshot(path=output_path, timeout=10000)
        else:
            await page.screenshot(path=output_path, timeout=10000)
            
        print(f"✅ [Instagram] Captura finalizada com sucesso!")
        return True

    except Exception as e:
        print(f"❌ [Instagram] Erro na captura inteligente: {e}")
        return False
