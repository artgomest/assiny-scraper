# assiny_scraper.py
import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone
import sys

def now_brasilia_str() -> str:
    """Retorna timestamp no formato 'dd/mm/aaaa - HH:MM' em horário de Brasília (UTC-3)."""
    tz_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(tz_brasilia).strftime("%d/%m/%Y - %H:%M")

# ====================== CONFIG ======================
ASSINY_URL = "https://admin.assiny.com.br"           # ajuste se necessário
TRANSACOES_PATH = "/organizations"            # caminho das transações (exemplo)
STORAGE_STATE_FILE = "google_login.json"             # login persistido
OUTPUT_CSV = "valor_assiny.csv"
STATE_FILE = "state/latest.json"

# Se quiser rastrear por produto, liste aqui:
PRODUTOS = [
    "Início Próspero",
    "Mentoria Individual",
    "Mentoria individual online",
    "Mentoria individual presencial",
]

# ====================== HELPERS ======================
def brl_to_float(txt: str) -> float:
    """Converte 'R$ 12.345,67' -> 12345.67"""
    if not txt:
        return 0.0
    # remove tudo que não for dígito, vírgula ou ponto
    s = re.sub(r"[^\d,.\-]", "", txt)
    # se tiver ponto e vírgula no padrão BR, troca vírgula por ponto e remove separador de milhar
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def ensure_dirs():
    Path("state").mkdir(exist_ok=True, parents=True)

def load_last_snapshot() -> Optional[Dict]:
    if not Path(STATE_FILE).exists():
        return None
    try:
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except:
        return None

def save_snapshot(snapshot: Dict):
    Path(STATE_FILE).write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

def snapshot_hash(snapshot: Dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def append_csv_row(row: Dict[str, str | float]):
    # Cria CSV (cabeçalho) se não existir
    header_cols = ["timestamp", "total"] + [f"prod_{i+1}" for i in range(len(PRODUTOS))]
    if not Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
            f.write(",".join(header_cols) + "\n")
    # Ordena e escreve
    values = [str(row.get(col, "")) for col in header_cols]
    with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
        f.write(",".join(values) + "\n")

def safe_text(page, selector: str, timeout: int = 5000) -> str:
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        return el.inner_text().strip()
    except:
        return ""

def unlock_transactions_page(page) -> bool:
    """
    Fluxo de desbloqueio atualizado e mais estável:
    - Verifica se a página já está liberada (link final visível);
    - Clica na sequência correta com esperas dinâmicas;
    - Retorna True mesmo que algumas etapas já estejam liberadas.
    """
    try:
        print("[INFO] Desbloqueio: iniciando verificação...")

        # Seletores principais
        second_btn = (
            "body > div:nth-child(1) > main > section.sectionContent > section > div > "
            "table > tbody > tr > td.sc-1b6ce047-7.cFNGWb.last-item > button"
        )
        third_btn = (
            "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > main > div > "
            "section > div > table > tbody > tr > td.sc-1b6ce047-7.cFNGWb.last-item > div > button"
        )
        final_link = (
            "body > div:nth-child(1) > div > div.sc-a939683d-0.kLVHsl > "
            "div.sc-a939683d-2.enkYbp > div.sc-a939683d-3.fzYEAU > div > a:nth-child(7)"
        )

        # 1️⃣ Verifica se o link final já está disponível
        if page.locator(final_link).count() and page.locator(final_link).is_visible():
            print("[STEP 1] Link final já disponível → clicando...")
            page.click(final_link)
            page.wait_for_load_state("networkidle")
            print("[SUCCESS] Página de transações liberada.")
            return True

        # 2️⃣ Clica no botão da tabela principal (espera ativa até 12s)
        if page.locator(second_btn).count():
            print("[STEP 2] Aguardando o botão da tabela principal ficar visível...")
            encontrado = False
            for _ in range(12):  # tenta 12 vezes (1s cada)
                if page.locator(second_btn).is_visible():
                    encontrado = True
                    break
                page.wait_for_timeout(1000)
            if encontrado:
                print("[STEP 2] Clicando no botão da tabela principal...")
                try:
                    page.click(second_btn, timeout=0)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2500)
                except Exception as e:
                    print(f"[WARN] Falha ao clicar no botão principal: {e}")
            else:
                print("[WARN] Botão da tabela principal não apareceu após 12s, seguindo assim mesmo.")
        else:
            print("[INFO] Botão principal não encontrado, talvez já esteja na próxima etapa.")

        # 3️⃣ Clica no botão interno (aguarda visibilidade até 6s)
        if page.locator(third_btn).count():
            try:
                page.wait_for_selector(third_btn, timeout=6000)
                print("[STEP 3] Clicando no botão interno da nova tabela...")
                page.click(third_btn)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
            except:
                print("[WARN] Botão interno não apareceu a tempo, seguindo...")
        else:
            print("[INFO] Botão interno não encontrado, talvez já esteja na tela final.")

        # 4️⃣ Clica no link final (aguarda visibilidade até 8s)
        try:
            page.wait_for_selector(final_link, timeout=8000)
            print("[STEP 4] Clicando no link final...")
            page.click(final_link)
            page.wait_for_load_state("networkidle")
            print("[SUCCESS] Página de transações liberada.")
            return True
        except:
            print("[INFO] Link final não apareceu, talvez já esteja na página de destino.")

        return True

    except Exception as e:
        print(f"[ERROR] Falha no desbloqueio: {e}")
        return False


from datetime import datetime

def aplicar_filtro_calendario(page):
    """
    Seleciona o intervalo fixo de 1º de janeiro de 2025 até 10 de outubro de 2025.
    Clica corretamente no '1' do calendário que contém 'Janeiro 2025' e aplica o filtro.
    """
    from datetime import datetime
    import unicodedata

    try:
        hoje = datetime.now()
        mes_inicial = "janeiro"
        ano_inicial = "2025"

        print(f"[STEP] Aplicando filtro via calendário (01/{mes_inicial.capitalize()}/{ano_inicial} → {hoje.strftime('%d/%m/%Y')})")

        # 1️⃣ Abre o seletor de período
        filtro_botao = page.locator(
            "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
            "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
            "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button"
        )
        filtro_botao.wait_for(state="visible", timeout=45000)
        filtro_botao.click()
        page.wait_for_timeout(1500)

        # Função auxiliar para normalizar texto (remove acentos, deixa minúsculo)
        def normalizar(txt):
            return "".join(
                c for c in unicodedata.normalize("NFD", txt.strip().lower())
                if unicodedata.category(c) != "Mn"
            )

        # 2️⃣ Retrocede até exibir Janeiro/2025 em algum calendário
        tentativas = 0
        while True:
            captions = page.locator(".rdp-caption_label").all_inner_texts()
            captions_norm = [normalizar(cap) for cap in captions]
            if any(mes_inicial in cap and ano_inicial in cap for cap in captions_norm):
                print(f"[OK] Encontrado mês inicial nos calendários: {captions_norm}")
                break
            page.click("button[name='previous-month']")
            page.wait_for_timeout(200)
            tentativas += 1
            if tentativas > 60:
                raise Exception(f"Não encontrou {mes_inicial}/{ano_inicial} após 60 tentativas")

        # 3️⃣ Localiza o container do mês 'Janeiro 2025' e clica no dia 1 exato dentro dele
        meses = page.locator(".rdp-month")
        clicou = False

        for i in range(meses.count()):
            try:
                caption = meses.nth(i).locator(".rdp-caption_label")
                if caption.count() == 0:
                    continue
                caption_text = normalizar(caption.first.inner_text())
                if mes_inicial in caption_text and ano_inicial in caption_text:
                    print(f"[OK] Container correto localizado: {caption_text}")

                    # Encontra todos os dias e garante que o texto seja exatamente "1"
                    dias = meses.nth(i).locator(".rdp-day")
                    for j in range(dias.count()):
                        dia = dias.nth(j)
                        dia_texto = dia.inner_text().strip()
                        if dia_texto == "1":
                            dia.scroll_into_view_if_needed()
                            dia.click(force=True)
                            print(f"[OK] Clicou no dia 1 exato de {mes_inicial}/{ano_inicial}.")
                            clicou = True
                            break
                    break
            except Exception as e:
                print(f"[DEBUG] Erro ao tentar clicar no mês {i}: {e}")

        if not clicou:
            raise Exception("Não conseguiu clicar no dia 1 exato de Janeiro/2025.")

        page.wait_for_timeout(800)

        # 4️⃣ (opcional) Se quiser, pode clicar direto em “Aplicar”
        aplicar_btn = (
            ".Button-apply > button.sc-8a29c332-0.kjexZj.size-sm.radius-rounded."
            "type-accent.width-stretch.iconPosition-left.periodButton"
        )
        page.locator(aplicar_btn).click(force=True)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        print("[OK] Filtro de calendário (Janeiro/2025 → Atual) aplicado com sucesso.")

    except Exception as e:
        print(f"[ERROR] Falha ao aplicar filtro via calendário: {e}")


def clear_product_selection(page):
    """Remove qualquer seleção anterior no react-select (multi ou single)."""
    try:
        # Remove chips se existirem
        for _ in range(10):
            remover = page.locator(".react-select__multi-value__remove")
            if remover.count() == 0:
                break
            remover.first.click()
            page.wait_for_timeout(120)

        # Botão de limpar (single select)
        clear_btn = page.locator(".react-select__clear-indicator")
        if clear_btn.count() > 0 and clear_btn.first.is_visible():
            clear_btn.first.click(force=True)
            page.wait_for_timeout(300)

        # Reabrir o campo pra garantir foco
        value_container = (
            "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
            "section.sectionContent > div > div.sc-901aedfc-0.hankki > "
            "div.sc-b1ed7421-0.lbZwDZ > div.sc-b1ed7421-2.eEgcfp > div > "
            "div.sc-b1ed7421-9.jdpVbC > div > div > div.filter-middle_selects > "
            "div:nth-child(2) > div > div > div.react-select__value-container.css-1lm0gyh"
        )
        page.click(value_container)
        page.wait_for_timeout(300)
    except Exception as e:
        print(f"[DEBUG] clear_product_selection: {e}")

def select_product_option(page, nome):
    """Abre o dropdown, digita e clica a opção exata no menu do react-select."""
    # Abre o dropdown (seletor que você passou)
    value_container = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-b1ed7421-0.lbZwDZ > div.sc-b1ed7421-2.eEgcfp > div > "
        "div.sc-b1ed7421-9.jdpVbC > div > div > div.filter-middle_selects > "
        "div:nth-child(2) > div > div > div.react-select__value-container.css-1lm0gyh"
    )
    page.click(value_container)
    page.wait_for_timeout(150)

    # Digita o nome e espera o menu abrir
    page.keyboard.press("Control+A")
    page.keyboard.type(nome)
    page.wait_for_selector(".react-select__menu", timeout=5000)

    # Clica a opção exata no menu
    menu_option = page.locator(".react-select__menu").get_by_text(nome, exact=True)
    menu_option.click(force=True)
    page.wait_for_timeout(200)

def apply_filters_panel(page):
    """Clica no botão Aplicar do painel de filtros."""
    aplicar_filtro_btn = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
        "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-b1ed7421-0.lbZwDZ > div.sc-b1ed7421-2.eEgcfp > div > "
        "div.sc-b1ed7421-5.kALddI > button"
    )
    btn = page.locator(aplicar_filtro_btn)
    btn.click()
    page.wait_for_timeout(400)
    # clica novamente se ainda estiver visível
    if btn.is_visible():
        btn.click()
    page.wait_for_timeout(800)

def wait_for_valor_atualizado(page, selector: str, timeout_ms: int = 15000):
    print("[INFO] Aguardando valor 'R$' aparecer no campo...")
    inicio = datetime.now()
    while (datetime.now() - inicio).total_seconds() * 1000 < timeout_ms:
        txt = safe_text(page, selector)
        if "R$" in txt:
            print(f"[OK] Valor carregado: {txt}")
            return txt
        page.wait_for_timeout(500)
    print("[WARN] Tempo limite atingido, 'R$' não encontrado.")
    return safe_text(page, selector)

# ====================== SCRAPER ======================
def fetch_snapshot(page) -> Dict:
    page.goto(ASSINY_URL + TRANSACOES_PATH, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    unlock_transactions_page(page)

    # Aguarda página carregar completamente após desbloqueio
    page.wait_for_load_state("networkidle")

    # ===============================
    # (A) Selecionar "Desde Sempre"
    # ===============================
    try:
        aplicar_filtro_calendario(page)

        # 4️⃣ validação visual: verificar se o filtro foi aplicado
        try:
            filtro_label = (
                "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
                "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
                "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button"
            )

            page.wait_for_selector(filtro_label, timeout=10000)
            filtro_text = page.locator(filtro_label).inner_text().strip()

            if "-" in filtro_text:
                print(f"[OK] Filtro de data aplicado com sucesso → '{filtro_text}'")
            else:
                print(f"[WARN] O filtro parece não ter sido aplicado corretamente. Texto atual: '{filtro_text}'")
        except Exception as e:
            print(f"[WARN] Não foi possível validar o filtro aplicado: {e}")

        print("[OK] Filtro 'Desde sempre' aplicado com sucesso.")

    except Exception as e:
        print(f"[WARN] Falha ao aplicar filtro de data: {e}")


    # ===============================
    # (B) Ler valor líquido total (com espera dinâmica)
    # ===============================
    total_selector = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-6b5fc9f9-0.fgkMrj > "
        "div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > "
        "div.sc-6b5fc9f9-7.blobef > div:nth-child(1) > div"
    )

    total_txt = wait_for_valor_atualizado(page, total_selector)
    total_val = brl_to_float(total_txt)

    # ===============================
    # (C) Filtro por produto (robusto)
    # ===============================
    produtos_vals: List[float] = []

    # botão que abre o painel de filtros
    open_filters_btn = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > button"
    )

    for nome in PRODUTOS:
        try:
            print(f"[INFO] Aplicando filtro de produto: {nome}")

            # Abre painel
            page.click(open_filters_btn)
            page.wait_for_timeout(700)

            # Limpa seleção anterior
            clear_product_selection(page)

            # Seleciona o produto exato
            select_product_option(page, nome)

            # Aplica (com dupla tentativa)
            apply_filters_panel(page)
            page.wait_for_timeout(1000)

            # Espera valor renderizar
            curr_val_txt = wait_for_valor_atualizado(page, total_selector)

            # Se falhou, tenta forçar render
            if not curr_val_txt or "R$" not in curr_val_txt:
                print("[INFO] Tentando forçar render clicando fora do painel...")
                page.mouse.click(50, 50)
                page.wait_for_timeout(1500)
                curr_val_txt = wait_for_valor_atualizado(page, total_selector)

            if not curr_val_txt:
                print(f"[WARN] Nenhum valor retornado para '{nome}', aplicando 0.0")
                produtos_vals.append(0.0)
                continue

            # Converte valor capturado
            p_val = brl_to_float(curr_val_txt)
            produtos_vals.append(p_val)
            print(f"[OK] Valor final para '{nome}': {p_val}")

        except Exception as e:
            print(f"[ERROR] Falha ao coletar produto '{nome}': {e}")
            produtos_vals.append(0.0)

    # ===============================
    # (D) Monta snapshot final
    # ===============================
    snapshot: Dict[str, float | str] = {
        "timestamp": now_brasilia_str(),
        "total": round(total_val, 2),
    }

    for i, val in enumerate(produtos_vals):
        snapshot[f"prod_{i+1}"] = round(val, 2)

    print(f"[SUMMARY] Snapshot final: {snapshot}")
    return snapshot


def main():
    with sync_playwright() as p:
        # 🔹 Importante: carregar o storage_state antes de criar a página
        browser = p.chromium.launch(headless=("--headed" not in sys.argv))
        context = browser.new_context(storage_state="google_login.json")
        page = context.new_page()

        # 🔹 Acesse diretamente o painel já autenticado
        page.goto("https://admin.assiny.com.br")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        print("[INFO] Página carregada, verificando autenticação...")

        # Se ainda estiver na tela de login, logins expiraram
        if "login" in page.url:
            print("[ERROR] Sessão expirada. É necessário gerar um novo google_login.json.")
            return


        print("✅ Login carregado com sucesso!")
        snapshot = fetch_snapshot(page)

        context.close()
        browser.close()

    # ======================
    #  Comparação e registro
    # ======================
    ensure_dirs()
    last_snapshot = load_last_snapshot()
    last_hash = snapshot_hash(last_snapshot) if last_snapshot else None

    current_hash = snapshot_hash(snapshot)
    changed = current_hash != last_hash

    if changed:
        append_csv_row(snapshot)
        save_snapshot(snapshot)
        print("[INFO] Mudança detectada. CSV e estado atualizados.")

        # Commit/push automático no GitHub Actions
        try:
            os.system('git config user.name "github-actions"')
            os.system('git config user.email "github-actions@github.com"')
            os.system(f'git add "{OUTPUT_CSV}" "{STATE_FILE}"')
            os.system('git commit -m "assiny-scraper: mudança detectada, histórico atualizado"')
            os.system('git pull --rebase origin main')
            os.system('git push origin main')

        except Exception as e:
            print(f"[WARN] Falha ao commitar/push: {e}")
    else:
        print("[INFO] Sem mudanças. Nada a registrar.")

if __name__ == "__main__":
    main()
