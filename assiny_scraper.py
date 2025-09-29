# assiny_scraper.py
from playwright.sync_api import sync_playwright
from datetime import datetime
import time
import csv
import json
import os

# Arquivo de storage_state será escrito a partir do secret
STORAGE_STATE_FILE = "google_login.json"

# Conteúdo do secret (JSON em string) - nas Actions vem por variável de ambiente
storage_state_json = os.environ.get("STORAGE_STATE_JSON", "")

if storage_state_json:
    # grava o google_login.json antes de rodar
    with open(STORAGE_STATE_FILE, "w", encoding="utf-8") as f:
        f.write(storage_state_json)

# URL da página de transações
URL_ASSINY = "https://admin.assiny.com.br/organizations/51082a1f-ee65-47a7-92ef-6f49b7c14134/projects/148350ac-61bc-42b7-87ee-9c8ba95c983c/financial/transactions"

# Seletor do botão do filtro de data (ajuste se mudar)
SELECTOR_FILTRO_DATA = "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button > button"

# Seletor do valor final (o que você quer capturar)
SELECTOR_VALOR = "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-6b5fc9f9-0.fgkMrj > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div.sc-6b5fc9f9-7.blobef > div:nth-child(1) > div"

CSV_PATH = "valor_assiny.csv"

def append_csv(timestamp, valor):
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["DataHora", "Valor"])
        w.writerow([timestamp, valor])

def main():
    with sync_playwright() as p:
        # Em Actions, Linux headless
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_FILE)

        page = context.new_page()
        print("🌐 Acessando a página de transações...")
        page.goto(URL_ASSINY)
        page.wait_for_load_state("networkidle")

        print("📅 Abrindo filtro de data...")
        page.wait_for_selector(SELECTOR_FILTRO_DATA, timeout=20000)
        page.click(SELECTOR_FILTRO_DATA)

        print("📌 Selecionando 'Desde Sempre'...")
        page.get_by_text("Desde Sempre").click()

        print("📌 Aplicando Filtro...")
        # Existem 2 botões "Aplicar". Usamos o segundo.
        page.get_by_role("button", name="Aplicar").nth(1).click()

        print("⏳ Aguardando atualização...")
        time.sleep(5)

        print("🔍 Capturando valor final...")
        try:
            page.wait_for_selector(SELECTOR_VALOR, timeout=20000)
            valor = page.query_selector(SELECTOR_VALOR).inner_text().strip()
        except Exception as e:
            valor = f"ERRO: {str(e)}"

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"✅ [{ts}] Valor: {valor}")
        append_csv(ts, valor)

        browser.close()

if __name__ == "__main__":
    main()
