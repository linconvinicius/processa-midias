# Processador de Mídias Sociais

Projeto para automação de scraping e processamento de links de mídias sociais (Instagram, Twitter/X, Facebook).

## 🚀 Estrutura do Projeto

O projeto foi simplificado e estruturado em camadas para facilitar a manutenção:

```
processa-midias/
├── cli.py                # Ponto de entrada ÚNICO (Command Line Interface)
├── manual_login.py       # Utilitário para renovação manual de sessões
├── .env                  # Configurações de credenciais e Banco de Dados
└── src/
    ├── database/         # Camada de Dados (Repository Pattern)
    ├── services/         # Lógica de Negócio (Orquestração de Spiders)
    ├── scraper/          # Motores de Captura (Playwright Spiders)
    ├── legacy_adapter/   # Integração com sistema legado (C#)
    └── config/           # Configurações globais
```

## 🛠️ Como Usar (CLI)

Todas as operações de rotina devem ser feitas através do `cli.py`.

### 1. Ver Fila de Processamento
Visualize os links que aguardam captura:
```bash
python cli.py queue --limit 20
```

### 2. Processar Links
Processa um link específico (Scraping + Download + Adapter + Update DB):
```bash
python cli.py process --id 12345
```

Processa um lote de links pendentes:
```bash
python cli.py process --batch --limit 10 --platform twitter
```

### 3. Resetar Link
Reseta o status para Pendente (1) e limpa a referência à Matéria no banco:
```bash
python cli.py reset --id 12345
```

### 4. Verificar Conexão
Testa a conectividade com o SQL Server:
```bash
python cli.py verify
```

## 🔒 Gestão de Sessões
O projeto utiliza arquivos `.json` na raiz (`twitter_state.json`, etc.) para manter a sessão dos navegadores ativa. Caso uma rede social exija novo login:
1. Execute `python manual_login.py`.
2. Realize o login no navegador que será aberto.
3. Feche o navegador para salvar o novo estado.

## 📋 Requisitos
- Python 3.12+
- Playwright (`playwright install chromium`)
- Driver ODBC 17/18 para SQL Server
