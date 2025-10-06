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

def formatar_timestamp(data=None):
    tz = timezone(timedelta(hours=-3))
    if data is None:
        data = datetime.now(tz)
    return data.strftime("%Y-%m-%d %H:%M:%S")

def update_csv(dados):
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

    linhas = []
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header_existente = next(reader)
            if header_existente != header:
                 raise ValueError("O cabeçalho do CSV não corresponde ao esperado.")
            linhas = list(reader)
        except StopIteration:
            pass

    if not linhas:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if os.path.getsize(CSV_PATH) == 0:
                writer.writerow(header)
            writer.writerow(dados_para_escrever)
        print("CSV atualizado com a primeira linha de dados.")
        return

    try:
        ultimo_timestamp_str = linhas[-1][0]
        ultimo_timestamp = datetime.strptime(ultimo_timestamp_str, "%Y-%m-%d %H:%M:%S")
        data_atual = datetime.now(timezone(timedelta(hours=-3)))

        if ultimo_timestamp.date() == data_atual.date():
            linhas[-1] = dados_para_escrever
            print("CSV atualizado: última linha sobrescrita.")
        else:
            linhas.append(dados_para_escrever)
            print("CSV atualizado: nova linha adicionada para o novo dia.")
    except (IndexError, ValueError) as e:
        print(f"Erro ao processar o CSV: {e}. Adicionando como nova linha.")
        linhas.append(dados_para_escrever)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(linhas)

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

    print("📌 Selecionando o período 'Hoje'...")
    page.get_by_text("Hoje", exact=True).wait_for(timeout=15000)
    page.get_by_text("Hoje", exact=True).click()

    # A seleção de 'Hoje' pode fechar o modal e aplicar o filtro automaticamente.
    # Se o botão 'Aplicar' ainda estiver visível, clique nele.
    try:
        aplicar_button = page.get_by_role("button", name="Aplicar").nth(1)
        if aplicar_button.is_visible(timeout=5000): # Checa visibilidade por 5s
            print("✅ Aplicando filtro de data...")
            aplicar_button.click()
    except Exception:
        print("Botão 'Aplicar' não encontrado ou não visível, seguindo em frente.")

    page.wait_for_load_state("networkidle", timeout=60000)

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


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_FILE)
        context.set_default_timeout(60000)  # Aumenta o timeout para 60 segundos
        page = context.new_page()

        url = ("https://admin.assiny.com.br/organizations/51082a1f-ee65-47a7-92ef-6f49b7c14134/"
               "projects/148350ac-61bc-42b7-87ee-9c8ba95c983c/financial/transactions")

        # 1. Obter o valor total primeiro
        page.goto(url, wait_until="networkidle")

        aplicar_filtro_data(page)
        valor_total = extrair_valor(page)

        # 2. Obter valores para cada produto
        valores = []
        for produto in PRODUTOS:
            page.goto(url, wait_until="networkidle")

            aplicar_filtro_data(page)

            aplicar_filtro_produto(page, produto)

            # Pausa para garantir que o filtro seja aplicado e os dados atualizados.
            print("Aguardando a aplicação do filtro...")
            time.sleep(5)

            valores.append(extrair_valor(page))

        browser.close()

        update_csv([valor_total] + valores)
        print(f"✅ CSV atualizado com sucesso!")

if __name__ == "__main__":
    if os.environ.get("STORAGE_STATE_JSON"):
        with open(STORAGE_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(os.environ["STORAGE_STATE_JSON"])

    try:
        run()
    except Exception as e:
        print(f"Ocorreu um erro: {e}")
