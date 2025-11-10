#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assiny Scraper - Versão Melhorada
Extrai dados financeiros da plataforma Assiny

Melhorias implementadas:
- Logging estruturado
- Retry automático com decorators
- Variáveis de ambiente
- Type hints completos
- Tratamento robusto de erros
- Seletores organizados
- Validação de dados
"""

import json
import os
import re
import hashlib
import sys
import logging
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from functools import wraps

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError

# ====================== LOGGING SETUP ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ====================== CONFIG ======================
class Config:
    """Configurações centralizadas com suporte a variáveis de ambiente"""
    ASSINY_URL: str = os.getenv('ASSINY_URL', 'https://admin.assiny.com.br')
    TRANSACOES_PATH: str = '/organizations'
    STORAGE_STATE_FILE: str = os.getenv('STORAGE_STATE', 'google_login.json')
    OUTPUT_CSV: str = os.getenv('OUTPUT_CSV', 'valor_assiny.csv')
    STATE_FILE: str = 'state/latest.json'
    HEADLESS: bool = os.getenv('HEADLESS', 'true').lower() == 'true' or '--headed' not in sys.argv
    
    # Timeouts em milissegundos
    DEFAULT_TIMEOUT: int = int(os.getenv('DEFAULT_TIMEOUT', '30000'))
    NETWORK_TIMEOUT: int = int(os.getenv('NETWORK_TIMEOUT', '60000'))
    
    # Retry configuration
    MAX_RETRIES: int = int(os.getenv('MAX_RETRIES', '3'))
    RETRY_DELAY: int = int(os.getenv('RETRY_DELAY', '2'))  # segundos
    
    # Produtos para rastreamento
    PRODUTOS: List[str] = [
        "Início Próspero",
        "Mentoria Individual",
        "Mentoria individual online",
        "Mentoria individual presencial",
    ]

# ====================== SELECTORS ======================
class Selectors:
    """Seletores CSS organizados e documentados"""
    
    # Botões de navegação para desbloqueio
    SECOND_BTN = (
        "body > div:nth-child(1) > main > section.sectionContent > section > div > "
        "table > tbody > tr > td.sc-1b6ce047-7.cFNGWb.last-item > button"
    )
    THIRD_BTN = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > main > div > "
        "section > div > table > tbody > tr > td.sc-1b6ce047-7.cFNGWb.last-item > div > button"
    )
    FINAL_LINK = (
        "body > div:nth-child(1) > div > div.sc-a939683d-0.kLVHsl > "
        "div.sc-a939683d-2.enkYbp > div.sc-a939683d-3.fzYEAU > div > a:nth-child(7)"
    )
    
    # Valores financeiros
    VALOR_LIQUIDO = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-6b5fc9f9-0.fgkMrj > "
        "div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > "
        "div.sc-6b5fc9f9-7.blobef > div:nth-child(1) > div"
    )
    
    # Filtros
    FILTRO_BTN = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
        "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button"
    )
    FILTRO_LABEL = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
        "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > div > div > button"
    )
    OPEN_FILTERS_BTN = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-901aedfc-2.jJUZpK > span:nth-child(2) > button"
    )
    APLICAR_FILTRO_BTN = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > "
        "div > section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-b1ed7421-0.lbZwDZ > div.sc-b1ed7421-2.eEgcfp > div > "
        "div.sc-b1ed7421-5.kALddI > button"
    )
    
    # Produto selector
    PRODUTO_VALUE_CONTAINER = (
        "body > div:nth-child(1) > div > div.sc-88f1a04b-3.waZHj > main > div > div > "
        "section.sectionContent > div > div.sc-901aedfc-0.hankki > "
        "div.sc-b1ed7421-0.lbZwDZ > div.sc-b1ed7421-2.eEgcfp > div > "
        "div.sc-b1ed7421-9.jdpVbC > div > div > div.filter-middle_selects > "
        "div:nth-child(2) > div > div > div.react-select__value-container.css-1lm0gyh"
    )
    PRODUTO_MENU = ".react-select__menu"
    PRODUTO_CLEAR = ".react-select__clear-indicator"
    PRODUTO_MULTI_REMOVE = ".react-select__multi-value__remove"
    
    # Calendário
    CALENDAR_CAPTION = ".rdp-caption_label"
    CALENDAR_MONTH = ".rdp-month"
    CALENDAR_DAY = ".rdp-day"
    CALENDAR_PREV_BTN = "button[name='previous-month']"
    CALENDAR_APPLY_BTN = (
        ".Button-apply > button.sc-8a29c332-0.kjexZj.size-sm.radius-rounded."
        "type-accent.width-stretch.iconPosition-left.periodButton"
    )

# ====================== DECORATORS ======================
def retry(max_attempts: int = 3, delay: int = 2, exceptions: tuple = (Exception,)):
    """
    Decorator para retry automático em caso de falhas
    
    Args:
        max_attempts: Número máximo de tentativas
        delay: Tempo de espera entre tentativas (segundos)
        exceptions: Tupla de exceções que devem acionar retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} falhou após {max_attempts} tentativas")
                        raise
                    logger.warning(
                        f"{func.__name__} - Tentativa {attempt}/{max_attempts} falhou: {e}. "
                        f"Retentando em {delay}s..."
                    )
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

# ====================== HELPERS ======================
def now_brasilia_str() -> str:
    """Retorna timestamp no formato 'dd/mm/aaaa - HH:MM' em horário de Brasília (UTC-3)"""
    tz_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(tz_brasilia).strftime("%d/%m/%Y - %H:%M")

def normalizar_texto(txt: str) -> str:
    """Remove acentos e normaliza texto para comparação"""
    return "".join(
        c for c in unicodedata.normalize("NFD", txt.strip().lower())
        if unicodedata.category(c) != "Mn"
    )

def brl_to_float(txt: str) -> float:
    """
    Converte string brasileira para float
    Exemplo: 'R$ 12.345,67' -> 12345.67
    """
    if not txt:
        return 0.0
    
    # Remove tudo que não for dígito, vírgula ou ponto
    s = re.sub(r"[^\d,.\-]", "", txt)
    
    # Trata padrão brasileiro (ponto para milhar, vírgula para decimal)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    
    try:
        return float(s)
    except ValueError:
        logger.warning(f"Não foi possível converter '{txt}' para float")
        return 0.0

def ensure_dirs() -> None:
    """Cria diretórios necessários"""
    Path("state").mkdir(exist_ok=True, parents=True)
    logger.debug("Diretórios verificados/criados")

def load_last_snapshot() -> Optional[Dict]:
    """Carrega último snapshot salvo"""
    if not Path(Config.STATE_FILE).exists():
        logger.info("Nenhum snapshot anterior encontrado")
        return None
    try:
        snapshot = json.loads(Path(Config.STATE_FILE).read_text(encoding="utf-8"))
        logger.info("Snapshot anterior carregado com sucesso")
        return snapshot
    except Exception as e:
        logger.error(f"Erro ao carregar snapshot: {e}")
        return None

def save_snapshot(snapshot: Dict) -> None:
    """Salva snapshot atual"""
    try:
        Path(Config.STATE_FILE).write_text(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8"
        )
        logger.info("Snapshot salvo com sucesso")
    except Exception as e:
        logger.error(f"Erro ao salvar snapshot: {e}")
        raise

def snapshot_hash(snapshot: Dict) -> str:
    """Gera hash MD5 do snapshot para detecção de mudanças"""
    if not snapshot:
        return ""
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def validate_snapshot(snapshot: Dict) -> bool:
    """
    Valida se snapshot contém dados válidos
    
    Returns:
        True se válido, False caso contrário
    """
    required_keys = ['timestamp', 'total']
    
    if not all(key in snapshot for key in required_keys):
        logger.error(f"Snapshot inválido: faltam keys obrigatórias {required_keys}")
        return False
    
    if not isinstance(snapshot['total'], (int, float)):
        logger.error(f"Valor 'total' inválido: {snapshot['total']}")
        return False
    
    if snapshot['total'] < 0:
        logger.warning("Valor total é negativo - pode ser um erro")
    
    return True

def append_csv_row(row: Dict[str, Any]) -> None:
    """Adiciona linha ao CSV de histórico"""
    try:
        header_cols = ["timestamp", "total"] + [
            f"prod_{i+1}" for i in range(len(Config.PRODUTOS))
        ]
        
        # Cria CSV com cabeçalho se não existir
        if not Path(Config.OUTPUT_CSV).exists():
            with open(Config.OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write(",".join(header_cols) + "\n")
            logger.info(f"Arquivo CSV criado: {Config.OUTPUT_CSV}")
        
        # Escreve linha
        values = [str(row.get(col, "")) for col in header_cols]
        with open(Config.OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(",".join(values) + "\n")
        
        logger.info(f"Linha adicionada ao CSV: {row['timestamp']}")
    except Exception as e:
        logger.error(f"Erro ao escrever CSV: {e}")
        raise

def safe_text(page: Page, selector: str, timeout: int = 5000) -> str:
    """
    Extrai texto de elemento com tratamento de erro
    
    Returns:
        Texto do elemento ou string vazia em caso de erro
    """
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        return el.inner_text().strip()
    except PlaywrightTimeoutError:
        logger.debug(f"Timeout ao aguardar elemento: {selector}")
        return ""
    except Exception as e:
        logger.debug(f"Erro ao extrair texto: {e}")
        return ""

def wait_for_valor_atualizado(page: Page, selector: str, timeout_ms: int = 15000) -> str:
    """
    Aguarda valor monetário aparecer no campo
    
    Returns:
        Texto do valor ou string vazia em caso de timeout
    """
    logger.info("Aguardando valor 'R$' aparecer no campo...")
    inicio = datetime.now()
    
    while (datetime.now() - inicio).total_seconds() * 1000 < timeout_ms:
        txt = safe_text(page, selector, timeout=500)
                 if "R$" in txt:
