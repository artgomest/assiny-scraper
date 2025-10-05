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
SELECTOR_VALOR_LIQUIDO = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                         "section.sectionContent > div > div.sc-6b5fc9f9-0.fgkMrj > div:nth-child(1) > "
                         "div:nth-child(1) > div:nth-child(1) > div.sc-6b5fc9f9-7.blobef > div:nth-child(1) > div")

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
    seletor_periodo = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                       "section.sectionContent > div.sc-38a05be3-7.hWHaLI > div.sc-901aedfc-0.hankki > "
                       "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button > button")
    page.wait_for_selector(seletor_periodo, timeout=20000)
    page.locator(seletor_periodo).click()

    print("📌 Selecionando 'Desde sempre'...")
    page.get_by_text("Desde sempre", exact=True).click()

    print("✅ Aplicando filtro de data...")
    page.get_by_role("button", name="Aplicar").nth(1).click()
    page.wait_for_load_state("networkidle", timeout=20000)

def aplicar_filtro_produto(page, produto):
    print(f"🎯 Aplicando filtro de produto: {produto}")
    botao_filtro = "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > button"
    page.wait_for_selector(botao_filtro, timeout=15000)
    page.locator(botao_filtro).click()

    select_box = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                  "section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-b1ed7421-0.lbZwDZ > "
                  "div.sc-b1ed7421-2.eEgcfp > div > div.sc-b1ed7421-9.jdpVbC > div > div > "
                  "div.filter-middle_selects > div:nth-child(2) > div > div")
    page.wait_for_selector(select_box, timeout=15000)
    page.locator(select_box).click()

    page.get_by_text(produto, exact=True).click()

    page.get_by_role("button", name="Aplicar").click()
    page.wait_for_load_state("networkidle", timeout=20000)

def limpar_filtro(page):
    try:
        limpar_button = page.get_by_text("Limpar Filtro", exact=True)
        limpar_button.wait_for(timeout=5000)
        limpar_button.click()
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        print(f"ⓘ Não foi possível limpar o filtro (provavelmente não havia um): {e}")
        pass

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_FILE)
        page = context.new_page()

        url = ("https://admin.assiny.com.br/organizations/51082a1f-ee65-47a7-92ef-6f49b7c14134/"
               "projects/148350ac-61bc-42b7-87ee-9c8ba95c983c/financial/transactions")

        print("🚀 Acessando a página...")
        page.goto(url, wait_until="networkidle", timeout=60000)

        aplicar_filtro_data(page)

        valor_total = extrair_valor(page)

        valores = []
        for produto in PRODUTOS:
            limpar_filtro(page)
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
