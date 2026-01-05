import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.scraper.core.browser import BrowserManager

async def manual_login_flow():
    print("🚀 Iniciando Modo de Login Manual Unificado...")
    print("ℹ️  O navegador vai abrir uma janela.")
    print("👉  Nessa MESMA janela, abra abas e faça login em:")
    print("    1. Twitter/X (x.com)")
    print("    2. Instagram (instagram.com)")
    print("    3. Facebook (facebook.com)")
    print("    (Você pode fazer apenas um ou todos, conforme precisar)")
    
    manager = BrowserManager()
    manager.settings.HEADLESS = False 
    
    try:
        # Ask user which state to load as base
        print("\n📂 Carregar sessão existente como base?")
        print("1. Twitter")
        print("2. Instagram")
        print("3. Facebook")
        print("4. Nenhuma (Limpo)")
        choice = await asyncio.to_thread(input, "Escolha (1-4): ")
        
        base_state = None
        if choice == "1": base_state = "twitter_state.json"
        elif choice == "2": base_state = "instagram_state.json"
        elif choice == "3": base_state = "facebook_state.json"
        
        if base_state and not os.path.exists(base_state):
            print(f"⚠️ Arquivo {base_state} não encontrado. Iniciando limpo.")
            base_state = None

        context = await manager.new_context(storage_state=base_state) 
        page = await context.new_page()
        
        # Open the specific one chosen, or just FB as default
        start_url = "https://www.facebook.com/"
        if choice == "1": start_url = "https://x.com/"
        elif choice == "2": start_url = "https://www.instagram.com/"
        
        await page.goto(start_url) 
        
        print("\n⏳ NAVEGADOR ABERTO!")
        print("⚡ Realize os logins necessários. Você pode abrir novas abas para outros sites.")
        print("⌨️  QUANDO TERMINAR, VOLTE AQUI.")
        
        await asyncio.to_thread(input, ">> Pressione ENTER para selecionar o que salvar <<")
        
        print("\n💾 O que você deseja salvar?")
        print("T. Salvar TUDO (Atualiza as 3 redes)")
        print("F. Apenas Facebook")
        print("X. Apenas Twitter")
        print("I. Apenas Instagram")
        save_choice = await asyncio.to_thread(input, "Escolha (T/F/X/I): ")
        save_choice = save_choice.upper()

        files_to_save = []
        if save_choice == "T": files_to_save = ["twitter_state.json", "instagram_state.json", "facebook_state.json"]
        elif save_choice == "F": files_to_save = ["facebook_state.json"]
        elif save_choice == "X": files_to_save = ["twitter_state.json"]
        elif save_choice == "I": files_to_save = ["instagram_state.json"]
        
        for f in files_to_save:
            await context.storage_state(path=f)
            print(f"💾 Sessão salva: {f}")
            
        print("🎉 Pronto!")
            
    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(manual_login_flow())
