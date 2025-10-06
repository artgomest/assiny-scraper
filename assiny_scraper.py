from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone
import csv
import time
import os
import re
import unicodedata

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

def sanitize_filename(name):
    # Normaliza a string para decompor os caracteres acentuados
    nfkd_form = unicodedata.normalize('NFKD', name)
    # Mantém apenas os caracteres ASCII
    ascii_name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    # Remove caracteres não alfanuméricos e substitui espaços/hífens por underscore
    sanitized_name = re.sub(r'[^\w\s-]', '', ascii_name).strip()
    sanitized_name = re.sub(r'[-\s]+', '_', sanitized_name)
    return sanitized_name

def formatar_timestamp(data=None):
    tz = timezone(timedelta(hours=-3))
    if data is None:
        data = datetime.now(tz)
    return data.strftime("%Y-%m-%d %H:%M:%S")

def append_on_change_csv(dados):
    timestamp_atual = formatar_timestamp()
    dados_para_escrever = [timestamp_atual] + dados
    header = ["DataHoraGMT-3", "Valor Total"] + PRODUTOS

    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerow(dados_para_escrever)
        print("CSV criado e primeira linha inserida.")
        return

    ultima_linha_dados = None
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            next(reader)
            for row in reader:
                ultima_linha_dados = row
        except StopIteration:
            pass

    if not ultima_linha_dados:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(dados_para_escrever)
        print("Primeira linha de dados inserida no CSV.")
        return

    dados_antigos = ultima_linha_dados[1:]
    if dados_antigos != dados:
        print("Alteração detectada! Adicionando nova linha no CSV.")
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(dados_para_escrever)
    else:
        print("Nenhuma alteração detectada. Nenhum registro foi adicionado.")

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
    page.wait_for_selector(SELETOR_PERIODO, timeout=60000)
    page.locator(SELETOR_PERIODO).click()

    print("📌 Selecionando o período 'Desde sempre'...")
    page.get_by_text("Desde sempre", exact=True).wait_for(timeout=15000)
    page.get_by_text("Desde sempre", exact=True).click()

    print("✅ Aplicando filtro de data...")
    page.get_by_role("button", name="Aplicar").nth(1).click()

    page.wait_for_load_state("load", timeout=60000)

def aplicar_filtro_produto(page, produto):
    print(f"🎯 Aplicando filtro de produto: {produto}")
    BOTAO_FILTRO = "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > button"
    page.locator(BOTAO_FILTRO).click()

    SELECT_BOX = ("body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
                  "section.sectionContent > div > div.sc-901aedfc-0.hankki > div.sc-b1ed7421-0.lbZwDZ > "
                  "div.sc-b1ed7421-2.eEgcfp > div > div.sc-b1ed7421-9.jdpVbC > div > div > "
                  "div.filter-middle_selects > div:nth-child(2) > div > div")
    page.locator(SELECT_BOX).click()

    page.get_by_text(produto, exact=True).click()

    # Clica no botão "Aplicar" dentro do modal de filtro para evitar ambiguidade.
    MODAL_SELECTOR = "div.sc-b1ed7421-0.lbZwDZ"
    page.locator(MODAL_SELECTOR).get_by_role("button", name="Aplicar").click()


def run(page):
    url = ("https://admin.assiny.com.br/organizations/51082a1f-ee65-47a7-92ef-6f49b7c14134/"
           "projects/148350ac-61bc-42b7-87ee-9c8ba95c983c/financial/transactions")

    # 1. Obter o valor total primeiro
    page.goto(url, wait_until="load")

    aplicar_filtro_data(page)
    valor_total = extrair_valor(page)

    # 2. Obter valores para cada produto
    valores = []
    for produto in PRODUTOS:
        try:
            page.goto(url, wait_until="load")
            aplicar_filtro_data(page)

            valor_antes_filtro = extrair_valor(page)

            aplicar_filtro_produto(page, produto)

            print(f"Aguardando o valor mudar para o produto '{produto}'...")
            page.wait_for_function(
                f"() => document.querySelector('{SELECTOR_VALOR_LIQUIDO.replace('\"', '\\\"')}').innerText.trim() !== '{valor_antes_filtro}'",
                timeout=20000
            )

            valores.append(extrair_valor(page))
        except Exception as e:
            print(f"Erro ao processar o produto '{produto}': {e}")
            sanitized_product_name = sanitize_filename(produto)
            screenshot_path = f"error_{sanitized_product_name}.png"
            page.screenshot(path=screenshot_path)
            print(f"Screenshot de erro salvo em: {screenshot_path}")
            valores.append("ERRO")

    append_on_change_csv([valor_total] + valores)
    print("Ciclo de verificação concluído. Aguardando 10 segundos...")
    time.sleep(10)


if __name__ == "__main__":
    if os.environ.get("STORAGE_STATE_JSON"):
        with open(STORAGE_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(os.environ["STORAGE_STATE_JSON"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_FILE)
        context.set_default_timeout(60000)
        page = context.new_page()

        try:
            run(page)
        except Exception as e:
            print(f"Ocorreu um erro: {e}")
