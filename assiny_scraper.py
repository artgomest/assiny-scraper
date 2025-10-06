from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone
import csv
import time
import os

PRODUTOS = [
    "Início Próspero",
    "Mentoria Individual",
    "Mentoria individual online",
    "Mentoria individual presencial"
]

CSV_PATH = "valor_assiny.csv"
STORAGE_STATE_FILE = "google_login.json"

# Seletor exato para o Valor Líquido que você me passou
SELECTOR_VALOR_LIQUIDO = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-6b5fc9f9-0.fgkMrj > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div.sc-6b5fc9f9-7.blobef > div:nth-child(1) > div")

def formatar_timestamp():
    tz = timezone(timedelta(hours=-3))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def sobrescrever_csv(dados):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["DataHoraGMT-3", "Valor Total"] + PRODUTOS
        writer.writerow(header)
        writer.writerow(dados)

def extrair_valor(page):
    page.wait_for_selector(SELECTOR_VALOR_LIQUIDO, timeout=20000)
    raw = page.locator(SELECTOR_VALOR_LIQUIDO).inner_text().strip()
    return raw if raw else "N/A"

def aplicar_filtro_data(page):
    print("📅 Abrindo seletor de período...")
    # seletor exato do botão de período
    SELETOR_PERIODO = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                       "section.sectionContent > div.sc-38a05be3-7.hWHaLI > div.sc-901aedfc-0.hankki > "
                       "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button > button")
    page.wait_for_selector(SELETOR_PERIODO, timeout=20000)
    page.locator(SELETOR_PERIODO).click()

    print("📌 Esperando aparecer botão 'Desde Sempre'...")
    page.get_by_text("Desde sempre", exact=True).wait_for(timeout=15000)
    page.get_by_text("Desde sempre", exact=True).click()

    print("✅ Aplicando filtro de data...")
    page.get_by_role("button", name="Aplicar").nth(1).click()
    time.sleep(3)

def aplicar_filtro_produto(page, produto):
    print(f"🎯 Aplicando filtro de produto: {produto}")
    BOTAO_FILTRO = "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > button"
    page.wait_for_selector(BOTAO_FILTRO, timeout=15000)
    page.locator(BOTAO_FILTRO).click()
    time.sleep(1)

    SELECT_BOX = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                  "section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-b1ed7421-0.lbZwDZ > "
                  "div.sc-b1ed7421-2.eEgcfp > div > div.sc-b1ed7421-9.jdpVbC > div > div > "
                  "div.filter-middle_selects > div:nth-child(2) > div > div")
    page.wait_for_selector(SELECT_BOX, timeout=15000)
    page.locator(SELECT_BOX).click()
    time.sleep(1)

    page.get_by_text(produto, exact=True).click()
    time.sleep(1)

    page.get_by_role("button", name="Aplicar").click()
    time.sleep(3)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_FILE)
        page = context.new_page()

        url = ("https://admin.assiny.com.br/organizations/51082a1f-ee65-47a7-92ef-6f49b7c14134/"
               "projects/148350ac-61bc-42b7-87ee-9c8ba95c983c/financial/transactions")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        aplicar_filtro_data(page)

        valor_total = extrair_valor(page)

        valores = []
        for produto in PRODUTOS:
            aplicar_filtro_produto(page, produto)
            valores.append(extrair_valor(page))

        browser.close()

        timestamp = formatar_timestamp()
        sobrescrever_csv([timestamp, valor_total] + valores)
        print(f"✅ CSV atualizado em {timestamp}")

if __name__ == "__main__":
    if os.environ.get("STORAGE_STATE_JSON"):
        with open(STORAGE_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(os.environ["STORAGE_STATE_JSON"])
    run()
