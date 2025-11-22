import os
import logging
import time
import shutil
import re
from datetime import datetime
from collections import defaultdict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    InvalidSessionIdException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from locators import (
    ServopaLocators,
    ServopaGroupLocators,
    ServopaLanceLocators,
)
from pdf_parser import extract_canonical_cota, parse_cota_from_filename, verificar_e_corrigir_nomes_pdf

class CaptchaDetectedException(Exception):
    """Exceção customizada para quando um CAPTCHA é detectado."""
    pass

class InvalidCredentialsException(Exception):
    """Exceção customizada para erro de login por credenciais inválidas."""
    pass

def setup_logging():
    """Configura o sistema de logging para o projeto com handlers separados."""
    # Formatter padrão para ambos os handlers
    log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Handler para o log geral (INFO e acima)
    general_handler = logging.FileHandler("automacao.log", mode="a", encoding="utf-8")
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(log_formatter)

    # Handler apenas para erros (ERROR e acima)
    error_handler = logging.FileHandler("erros_lances_2.txt", mode="a", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(log_formatter)

    logging.basicConfig(
        level=logging.INFO, # Nível mais baixo para capturar tudo
        handlers=[
            general_handler,
            error_handler,
            logging.StreamHandler(), # Para a GUI
        ],
        force=True
    )

# Carregar variáveis de ambiente
def _get_normalized_path(env_var):
    path = os.getenv(env_var)
    if path:
        return os.path.normpath(path)
    return None

CPF_CNPJ = os.getenv("CPF_CNPJ")
SENHA = os.getenv("SENHA")
SERVOPA_URL = os.getenv("SERVOPA_URL")
SERVOPA_LANCES_URL = os.getenv("SERVOPA_LANCES_URL", "https://www.consorcioservopa.com.br/vendas/lances")
ERROS_FILE = os.getenv("ERROS_FILE", "erros_lances.txt")
LANCE_LIVRE_PERCENTUAL = os.getenv("LANCE_LIVRE_PERCENTUAL", "40")
LANCE_LIVRE_DESCONTAR_CARTA = os.getenv("LANCE_LIVRE_DESCONTAR_CARTA", "30")
GECKODRIVER_PATH = _get_normalized_path("GECKODRIVER_PATH")
FIREFOX_PROFILE_PATH = _get_normalized_path("FIREFOX_PROFILE_PATH")
DOWNLOAD_DIR = _get_normalized_path("DOWNLOAD_DIR")
FIREFOX_BINARY_PATH = _get_normalized_path("FIREFOX_BINARY_PATH")

def get_driver():
    """Configura e retorna uma instância do WebDriver do Firefox."""
    logging.info("Configurando instância do WebDriver...")
    if not all([GECKODRIVER_PATH, DOWNLOAD_DIR, FIREFOX_BINARY_PATH]):
        raise ValueError("Variáveis de ambiente essenciais (GECKODRIVER_PATH, DOWNLOAD_DIR, FIREFOX_BINARY_PATH) não definidas no .env")

    options = Options()
    options.binary_location = FIREFOX_BINARY_PATH
    if FIREFOX_PROFILE_PATH:
        logging.info(f"Usando perfil do Firefox: {FIREFOX_PROFILE_PATH}")
        options.add_argument("-profile")
        options.add_argument(FIREFOX_PROFILE_PATH)

    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", os.path.abspath(DOWNLOAD_DIR))
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf")
    options.set_preference("pdfjs.disabled", True)
    options.set_preference("network.cookie.sameSite.laxByDefault", False)
    options.set_preference("network.cookie.sameSite.noneRequiresSecure", False)

    service = Service(GECKODRIVER_PATH)
    try:
        driver = webdriver.Firefox(service=service, options=options)
        logging.info("WebDriver do Firefox iniciado com sucesso.")
        return driver
    except WebDriverException as e:
        logging.error(f"Falha ao iniciar o WebDriver: {e}")
        raise

# --- Funções de Apoio Robustas ---

def remover_loading(driver):
    """Remove o overlay 'pace-active' de forma direta e aguarda um instante."""
    try:
        logging.info("Removendo tela de loading ('pace-active')...")
        driver.execute_script("document.querySelector('.pace-active')?.remove();")
        time.sleep(0.4)  # Pequena pausa para a UI atualizar
    except Exception as e:
        logging.warning(f"Não foi possível remover o loading via JS: {e}")

def save_debug_artifacts(driver, base_dir, basename):
    """Salva screenshot (.png) e HTML (.html) para depuração inesperada."""
    try:
        os.makedirs(base_dir, exist_ok=True)
        png_path = os.path.join(base_dir, f"{basename}.png")
        html_path = os.path.join(base_dir, f"{basename}.html")
        try:
            driver.save_screenshot(png_path)
            logging.info(f"Screenshot de depuração salvo em: {png_path}")
        except Exception as e:
            logging.error(f"Não foi possível salvar screenshot: {e}")
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source or "")
            logging.info(f"HTML de depuração salvo em: {html_path}")
        except Exception as e:
            logging.error(f"Não foi possível salvar HTML de depuração: {e}")
    except Exception as e:
        logging.error(f"Falha ao preparar diretório de depuração: {e}")

def check_for_captcha(driver):
    """Verifica proativamente por CAPTCHA e lança uma exceção customizada."""
    try:
        WebDriverWait(driver, 2).until(EC.visibility_of_element_located(ServopaLocators.CAPTCHA))
        raise CaptchaDetectedException("CAPTCHA detectado na página.")
    except TimeoutException:
        pass

def aguardar_download_concluir(download_path, timeout=90):
    """Aguarda a conclusão do download de um arquivo PDF, verificando a estabilidade do tamanho."""
    logging.info(f"Monitorando pasta de downloads: {download_path}")
    start_time = time.time()
    time.sleep(2) # Espera inicial para o arquivo .part ser criado
    while time.time() - start_time < timeout:
        files = [f for f in os.listdir(download_path) if f.endswith(".pdf") and not f.endswith(".part")]
        if files:
            pdf_file = files[0]
            file_path = os.path.join(download_path, pdf_file)
            logging.info(f"Arquivo PDF '{pdf_file}' encontrado. Verificando estabilidade...")
            last_size = -1
            stable_count = 0
            stable_threshold = 3
            while time.time() - start_time < timeout:
                try:
                    current_size = os.path.getsize(file_path)
                    if current_size == last_size and current_size > 0:
                        stable_count += 1
                        if stable_count >= stable_threshold:
                            logging.info(f"Download do '{pdf_file}' concluído e estável.")
                            return pdf_file
                    else:
                        stable_count = 0
                    last_size = current_size
                except FileNotFoundError:
                    time.sleep(1)
                    continue
                time.sleep(1)
            raise TimeoutException(f"Tempo esgotado esperando a estabilização do arquivo '{pdf_file}'.")
        time.sleep(1)
    raise TimeoutException("Nenhum arquivo PDF apareceu na pasta de downloads.")

def aguardar_pdf_aparecer(download_path, timeout=4):
    """Verifica rapidamente se algum PDF apareceu na pasta de downloads.

    Retorna o nome do arquivo (string) se encontrado dentro do timeout; caso contrário, None.
    Não verifica estabilidade do tamanho, apenas presença.
    """
    logging.info(f"Verificação rápida por PDF (até {timeout}s) em: {download_path}")
    start = time.time()
    while time.time() - start < timeout:
        files = [f for f in os.listdir(download_path) if f.endswith('.pdf') and not f.endswith('.part')]
        if files:
            logging.info(f"PDF detectado rapidamente: {files[0]}")
            return files[0]
        time.sleep(0.3)
    return None

def sanitizar_nome_arquivo(nome):
    """Remove caracteres inválidos de um nome de arquivo."""
    return re.sub(r'[\\/:*?"<>|]', '_', nome)

def find_element(driver, by, value, timeout=10):
    """Busca um elemento, esperando explicitamente que ele esteja VISÍVEL."""
    try:
        return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))
    except TimeoutException:
        logging.warning(f"Elemento não ficou visível: {by}={value} dentro de {timeout}s.")
        return None

def click_element(driver, by, value, timeout=10):
    """Tenta clicar em um elemento, priorizando JavaScript por ser mais robusto contra interceptações."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception as e:
        logging.error(f"Falha crítica ao clicar no elemento {value} via JavaScript: {e}")
        return False

def click_first_available(driver, locators, timeout_each=6):
    """Tenta clicar no primeiro seletor que funcionar, com logs detalhados.

    locators: lista de tuplas (By, value)
    """
    for (by, value) in locators:
        logging.info(f"Tentando clicar no controle: by={by}, value={value}")
        try:
            element = WebDriverWait(driver, timeout_each).until(EC.element_to_be_clickable((by, value)))
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            except Exception:
                pass
            try:
                driver.execute_script("arguments[0].click();", element)
                time.sleep(0.2)
                return True
            except Exception as e_js:
                logging.warning(f"Clique via JS falhou para {value}: {e_js}")
                try:
                    element.click()
                    time.sleep(0.2)
                    return True
                except Exception as e_native:
                    logging.warning(f"Clique nativo falhou para {value}: {e_native}")
        except TimeoutException:
            logging.info(f"Controle não encontrado a tempo: {value}")
        except Exception as e:
            logging.warning(f"Falha ao preparar clique em {value}: {e}")
    logging.error("Nenhum seletor de clique funcionou dentre os fornecidos.")
    return False

def find_first_present(driver, locators, timeout_each=5):
    """Retorna o primeiro elemento PRESENTE no DOM dentre os locators informados, ou None.

    Observação: Alguns campos podem estar fora da viewport ou demorarem para ficar visíveis,
    por isso detectamos por presença e rolamos até eles antes de interagir.
    """
    for locator in locators:
        try:
            el = WebDriverWait(driver, timeout_each).until(EC.presence_of_element_located(locator))
            return el
        except Exception:
            continue
    return None
def type_text_and_verify(driver, by, value, text, timeout=10, retries=3, delay=0.2, is_password=False):
    """Preenche um campo de texto e verifica se o valor foi realmente aplicado.

    Estratégia:
    - clear + click + send_keys
    - validação por get_attribute('value'); para senha, aceita apenas comprimento>0
    - fallback: set via JavaScript e revalida
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            element = WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))
        except TimeoutException as e:
            last_error = e
            logging.warning(f"Campo não visível para digitação (tentativa {attempt}/{retries}): {by}={value}")
            continue

        try:
            try:
                element.clear()
            except Exception:
                pass
            try:
                element.click()
            except Exception:
                pass
            element.send_keys(text)
            time.sleep(delay)

            current = element.get_attribute("value") or ""
            if (is_password and len(current) > 0) or (not is_password and current.strip() == str(text)):
                return True

            # Fallback por JavaScript
            try:
                driver.execute_script("arguments[0].value = arguments[1];", element, text)
                time.sleep(delay)
                current = element.get_attribute("value") or ""
                if (is_password and len(current) > 0) or (not is_password and current.strip() == str(text)):
                    return True
            except Exception as js_e:
                last_error = js_e
        except Exception as e:
            last_error = e
            logging.warning(f"Falha ao digitar no campo (tentativa {attempt}/{retries}): {e}")

    logging.error(f"Não foi possível confirmar o preenchimento do campo {value}. Último erro: {last_error}")
    return False

# --- Funções de Lógica de Negócio ---

def login(driver):
    """Realiza o login no sistema, com verificações proativas."""
    logging.info(f"Acessando URL de login: {SERVOPA_URL}")
    driver.get(SERVOPA_URL)
    remover_loading(driver)
    check_for_captcha(driver)
    logging.info("Nenhum CAPTCHA detectado. Preenchendo credenciais com verificação...")
    try:
        if not type_text_and_verify(driver, *ServopaLocators.USERNAME_FIELD, CPF_CNPJ, is_password=False):
            raise Exception("Falha ao preencher o campo CPF/CNPJ com verificação.")
        if not type_text_and_verify(driver, *ServopaLocators.PASSWORD_FIELD, SENHA, is_password=True):
            raise Exception("Falha ao preencher o campo Senha com verificação.")

        if not click_element(driver, *ServopaLocators.LOGIN_BUTTON):
            raise Exception("Falha ao clicar no botão de login.")

        # --- DEBUG LOGIN ---
        current_url = driver.current_url
        logging.info(f"DEBUG LOGIN: URL após tentativa de login: {current_url}")

        # Verifica erro explícito de credenciais
        login_error_element = find_element(driver, *ServopaLocators.LOGIN_ERROR_MESSAGE, timeout=3)
        if login_error_element:
            logging.error(f"DEBUG LOGIN: Mensagem de erro de login encontrada: {login_error_element.text}")
            raise InvalidCredentialsException("Login falhou: CPF/CNPJ ou senha inválidos!")
        else:
            logging.info("DEBUG LOGIN: Nenhuma mensagem de erro de login visível.")

        # Se o login foi bem-sucedido, o LOGOUT_BUTTON deve estar visível
        try:
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located(ServopaLocators.LOGOUT_BUTTON))
            logging.info("DEBUG LOGIN: Botão de Logout visível. Login bem-sucedido.")
        except TimeoutException:
            logging.warning("DEBUG LOGIN: Botão de Logout NÃO visível após login. Possível falha ou redirecionamento inesperado.")

        logging.info("Login realizado (ou prosseguindo sem confirmação explícita de logout).")
        remover_loading(driver)
        return True
    except InvalidCredentialsException:
        # Propaga para permitir retentativas controladas no chamador
        raise
    except Exception as e:
        logging.error("Falha durante o preenchimento do login ou na confirmação.")
        check_for_captcha(driver)
        raise e

def _navegar_e_buscar_cota(driver, cota_info):
    """Navega via menus até a tela de busca e preenche os dados da cota."""
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']
    logging.info(f"Navegando via menu para a busca da cota {grupo}/{cota}-{digito}")

    # Clica no menu "Ferramentas Admin" - seletor robusto do script antigo
    if not click_element(driver, By.XPATH, "//a[contains(., 'Ferramentas Admin')]"):
        raise Exception("Falha ao clicar no menu 'Ferramentas Admin'")
    remover_loading(driver)

    # Clica no submenu "Buscar" - seletor robusto do script antigo
    if not click_element(driver, By.XPATH, "//a[@href='https://www.consorcioservopa.com.br/vendas/buscar']"):
        raise Exception("Falha ao clicar no submenu 'Buscar'")
    remover_loading(driver)

    # Preenche o formulário de busca
    logging.info(f"Preenchendo busca para Grupo: {grupo}, Cota: {cota}, Dígito: {digito}")
    find_element(driver, *ServopaGroupLocators.GROUP_INPUT).send_keys(grupo)
    find_element(driver, *ServopaGroupLocators.COTA_INPUT).send_keys(cota)
    find_element(driver, *ServopaGroupLocators.DIGITO_INPUT).send_keys(digito)

    logging.info("Clicando no botão de busca...")
    if not click_element(driver, *ServopaGroupLocators.SEARCH_GROUP_BUTTON):
        raise Exception("Falha ao clicar no botão de busca.")
    
    remover_loading(driver)
    logging.info("Busca realizada. Aguardando resultados...")
    return True

def run_automation_for_cota(driver, cota_info, consultor):
    """Orquestra o fluxo completo para uma única cota."""
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']
    logging.info(f"--- INICIANDO COTA {cota_info['original']} ---")
    try:
        _navegar_e_buscar_cota(driver, cota_info)

        logging.info("Procurando pela tabela de resultados...")
        result_body = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//tbody")))
        rows = result_body.find_elements(By.XPATH, ".//tr[@onclick]")
        logging.info(f"{len(rows)} linha(s) de resultado encontradas.")
        if not rows:
            return 'ERRO_BENIGNO', "Cota não encontrada na busca."

        cota_ativa_encontrada = False
        for i, row in enumerate(rows):
            logging.info(f"Verificando linha {i+1}...")
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 8:
                status_text = cells[7].text.strip().upper()
                logging.info(f"Status encontrado: '{status_text}'")
                if status_text == "ATIVO":
                    logging.info(f"Cota ATIVA encontrada. Clicando na linha...")
                    driver.execute_script("arguments[0].click();", row)
                    cota_ativa_encontrada = True
                    break
        
        if not cota_ativa_encontrada:
            return 'ERRO_BENIGNO', "Nenhuma cota com status 'ATIVO' foi encontrada."

        remover_loading(driver)
        logging.info("Página da cota carregada. Verificando status (rápido pelo header)...")
        # Verificação rápida do header do Extrato (1 leitura)
        try:
            header_el = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located(ServopaLanceLocators.EXTRATO_HEADER_ANY)
            )
            header_txt = (header_el.text or header_el.get_attribute('textContent') or '').strip().upper()
            if 'EXTRATO - CANCELADO' in header_txt:
                return 'ERRO_BENIGNO', "Extrato da cota está cancelado."
            if header_txt == 'EXTRATO':
                pass  # ok, segue
            else:
                logging.warning(f"Header de Extrato inesperado: '{header_txt}'. Aplicando verificação de fallback...")
                # Fallback para os seletores antigos se o texto estiver diferente/oculto
                if find_element(driver, *ServopaLanceLocators.EXTRATO_CANCELADO_HEADER, timeout=2):
                    return 'ERRO_BENIGNO', "Extrato da cota está cancelado."
                if not find_element(driver, *ServopaLanceLocators.EXTRATO_HEADER_NORMAL, timeout=3):
                    save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-extrato")
                    return 'ERRO_CRITICO', "Página de Extrato não carregou como esperado."
        except TimeoutException:
            logging.warning("Header de Extrato não encontrado rapidamente; aplicando verificação de fallback...")
            if find_element(driver, *ServopaLanceLocators.EXTRATO_CANCELADO_HEADER, timeout=2):
                return 'ERRO_BENIGNO', "Extrato da cota está cancelado."
            if not find_element(driver, *ServopaLanceLocators.EXTRATO_HEADER_NORMAL, timeout=3):
                save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-extrato")
                return 'ERRO_CRITICO', "Página de Extrato não carregou como esperado."
        # 3) Estado contemplado impede lance
        if find_element(driver, *ServopaLanceLocators.LANCE_CONTEMPLADO_ERROR, timeout=3):
            return 'ERRO_BENIGNO', "Cota já está contemplada."
        
        logging.info("Abrindo a página de lances diretamente pela URL (go to)...")
        try:
            driver.get(SERVOPA_LANCES_URL)
        except WebDriverException as nav_e:
            logging.error(f"Falha ao navegar para a página de lances: {nav_e}")
            return 'ERRO_CRITICO', f"Navegação para página de lances falhou: {nav_e}"

        remover_loading(driver)
        check_for_captcha(driver)
        try:
            # Aguarda indicadores principais da tela de lances
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tab-switcher"))
            )
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.ID, "btn_simular"))
            )
        except TimeoutException:
            save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-lances-load")
            return 'ERRO_CRITICO', "Página de lances não carregou corretamente (tab-switcher ausente)."

        if find_element(driver, *ServopaLanceLocators.LANCE_FIDELIDADE_TAB, timeout=2):
            return 'ERRO_BENIGNO', "A cota possui Lance Fidelidade e não pode ser processada."

        # Detecta tipo pelo TAB ativo, evitando confundir campos ocultos
        logging.info("Determinando tipo de lance pelo tab ativo...")
        tab_ativo = find_element(driver, *ServopaLanceLocators.LANCE_ACTIVE_TAB, timeout=6)
        tipo_tab = (tab_ativo.text or tab_ativo.get_attribute('textContent') or '').strip().upper() if tab_ativo else ''
        data_lance = tab_ativo.get_attribute('data-lance').upper() if (tab_ativo and tab_ativo.get_attribute('data-lance')) else ''

        is_livre = (data_lance == 'L') or ('LIVRE' in tipo_tab)
        if is_livre:
            logging.info("TAB ativo indica Lance Livre. Preenchendo percentual (40) e descontar carta (30)...")
            # Preencher Percentual (usar inputs VISÍVEIS)
            ok_percent = False
            for locator in [ServopaLanceLocators.LANCE_LIVRE_PERCENTUAL_INPUT, ServopaLanceLocators.LANCE_LIVRE_PERCENTUAL_INPUT_ALT]:
                el = find_element(driver, *locator, timeout=4)
                if el is not None and type_text_and_verify(driver, *locator, LANCE_LIVRE_PERCENTUAL, is_password=False):
                    ok_percent = True
                    break
            if not ok_percent:
                save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-preencher-percentual")
                return 'ERRO_CRITICO', "Falha ao preencher o campo de Percentual do Lance Livre."

            # Preencher Descontar Carta (VISÍVEL)
            el_desc = find_element(driver, *ServopaLanceLocators.LANCE_LIVRE_DESCONTAR_INPUT, timeout=4)
            if el_desc is None or not type_text_and_verify(driver, *ServopaLanceLocators.LANCE_LIVRE_DESCONTAR_INPUT, LANCE_LIVRE_DESCONTAR_CARTA, is_password=False):
                save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-preencher-descontar")
                return 'ERRO_CRITICO', "Falha ao preencher o campo 'Descontar da Carta' do Lance Livre."
        else:
            logging.info("TAB ativo indica Lance Fixo. Prosseguindo sem preencher campos.")
        
        logging.info("Simulando lance...")
        simular_locators = [
            ServopaLanceLocators.SIMULAR_BUTTON,
            (By.XPATH, "//a[@id='btn_simular']"),
            (By.XPATH, "//a[contains(normalize-space(.), 'Simular Lance')]")
        ]
        # Tenta clique robusto em 'Simular'
        if not click_first_available(driver, simular_locators, timeout_each=10):
            save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-simular")
            raise Exception("Falha ao acionar 'Simular Lance' (nenhum seletor funcionou).")

        # Aguarda recarregamento ou mudanças após simular
        time.sleep(0.5)
        remover_loading(driver)
        try:
            # Espera por algum sinal de mudança de tela: presença de 'Registrar' ou do input de protocolo
            WebDriverWait(driver, 12).until(
                lambda d: find_element(d, *ServopaLanceLocators.REGISTRAR_LINK, timeout=1)
                or find_element(d, *ServopaLanceLocators.REGISTRAR_BUTTON, timeout=1)
                or find_element(d, *ServopaLanceLocators.PROTOCOLO_ANTERIOR_INPUT, timeout=1)
            )
        except Exception:
            logging.info("Após 'Simular', sinais de mudança não apareceram a tempo; prosseguindo com verificações padrão.")
        if find_element(driver, *ServopaLanceLocators.PROTOCOLO_ANTERIOR_INPUT, timeout=3):
            return 'ERRO_BENIGNO', "Lance já realizado (protocolo anterior encontrado)."
        
        logging.info("Registrando lance e aguardando download...")
        # Tenta múltiplos seletores para maior robustez
        registrar_locators = [
            ServopaLanceLocators.REGISTRAR_BUTTON,
            ServopaLanceLocators.REGISTRAR_LINK,
            ServopaLanceLocators.REGISTRAR_ABSOLUTE,
        ]
        # Aguarda um curto período para o botão/ancora ficar habilitado após a simulação
        try:
            WebDriverWait(driver, 8).until(lambda d: any(
                WebDriverWait(d, 1).until(EC.element_to_be_clickable(loc),)
                for loc in registrar_locators
            ))
        except Exception:
            logging.info("Registrar ainda não clicável após simulação; tentaremos mesmo assim com fallbacks.")
        if not click_first_available(driver, registrar_locators, timeout_each=8):
            save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}-registrar")
            raise Exception("Falha ao acionar o comando 'Registrar' (nenhum seletor funcionou).")

        # Prioriza velocidade: tenta detectar PDF rapidamente; se não, checa modal; se não, espera completo
        quick_pdf = aguardar_pdf_aparecer(DOWNLOAD_DIR, timeout=4)
        if not quick_pdf:
            # Modal de bloqueio de assembleia (erro esperado)
            try:
                WebDriverWait(driver, 3).until(EC.presence_of_element_located(ServopaLanceLocators.MODAL_CONTAINER))
                modal_text_el = find_element(driver, *ServopaLanceLocators.MODAL_TEXT, timeout=2)
                modal_text = (modal_text_el.text if modal_text_el else '').strip()
                logging.info(f"Modal detectado após Registrar. Mensagem: {modal_text}")
                # Fecha o modal
                try:
                    ok_clicked = click_first_available(driver, [
                        ServopaLanceLocators.MODAL_OK_BUTTON,
                        ServopaLanceLocators.MODAL_OK_BUTTON_BY_TEXT
                    ], timeout_each=2)
                    if not ok_clicked:
                        logging.info("Não foi possível clicar no OK do modal via seletores padrão.")
                except Exception:
                    pass
                return 'ERRO_BENIGNO', f"Bloqueio de assembleia / modal após Registrar: {modal_text}"
            except TimeoutException:
                pass

        # Se quick_pdf apareceu ou não houve modal, aguarda a conclusão normal do download
        pdf_filename = aguardar_download_concluir(DOWNLOAD_DIR)
        nome_cliente = find_element(driver, *ServopaLanceLocators.NOME_CLIENTE_TEXT).text.strip()
        nome_cliente_sanitizado = sanitizar_nome_arquivo(nome_cliente)
        novo_nome = f"LANCE- {nome_cliente_sanitizado} {grupo}.{cota}-{digito}.pdf"
        caminho_destino = os.path.join("Lances", consultor, novo_nome)
        shutil.move(os.path.join(DOWNLOAD_DIR, pdf_filename), caminho_destino)
        logging.info(f"PDF salvo como: {caminho_destino}")
        return 'SUCESSO', "Lance registrado e PDF salvo com sucesso."
    except Exception as e:
        error_message = f"{type(e).__name__}: {e}"
        logging.error(f"Erro inesperado no fluxo da cota {cota_info['original']}: {error_message}", exc_info=True)
        save_debug_artifacts(driver, os.path.join("Lances", consultor), f"ERRO-{cota_info['original'].replace(',','-')}")
        return 'ERRO_CRITICO', error_message

def parse_lances_from_string(cotas_input):
    """Analisa a string de entrada de cotas e a converte em uma lista de dicionários canônicos.

    Retorna: (cotas_validas, linhas_invalidas_texto, linhas_invalidas_indexados)
    onde linhas_invalidas_indexados = [(numero_linha_1_based, texto)]
    """
    cotas = []
    linhas_invalidas = []
    linhas_invalidas_idx = []
    for idx, raw in enumerate(cotas_input.split("\n"), start=1):
        linha = (raw or '').strip()
        if not linha:
            continue
        canonical_cota = extract_canonical_cota(linha)
        if canonical_cota:
            grupo, cota, digito = canonical_cota
            cotas.append({"grupo": grupo, "cota": cota, "digito": digito, "original": linha})
        else:
            linhas_invalidas.append(linha)
            linhas_invalidas_idx.append((idx, linha))
    if linhas_invalidas:
        logging.warning(f"As seguintes linhas foram ignoradas (formato inválido): {linhas_invalidas}")
    return cotas, linhas_invalidas, linhas_invalidas_idx

def _classificar_benigno(mensagem: str) -> str:
    m = (mensagem or '').lower()
    if 'cota não encontrada' in m:
        return 'Cota Não Existe'
    if 'nenhuma cota com status' in m or 'não ativa' in m:
        return 'Cota Não Ativa'
    if 'protocolo anterior' in m:
        return 'Requer Protocolo'
    if 'fidelidade' in m:
        return 'Lance Fidelidade'
    if 'extrato da cota está cancelado' in m:
        return 'Extrato Cancelado'
    return 'Benigno'

def _classificar_critico(erro: str) -> str:
    # erro vem no formato "TipoException: msg" quando possível
    if not erro:
        return 'Erro Genérico'
    tipo = erro.split(':', 1)[0].strip()
    # Normaliza alguns nomes
    if 'TimeoutException' in tipo:
        return 'TimeoutException'
    if 'StaleElementReferenceException' in tipo:
        return 'StaleElementReferenceException'
    if 'WebDriverException' in tipo:
        return 'WebDriverException'
    if 'Falha ao acionar' in erro or 'clicar' in erro.lower():
        return 'Erro de Clique'
    return tipo or 'Erro Genérico'

def _escrever_relatorio_erros(consultor: str, linhas_invalidas_idx, buckets_benignos, buckets_criticos, resumo_sucesso, arquivo_saida):
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    linhas = []
    linhas.append("="*49)
    linhas.append(f"Relatório de Erros da Execução - {agora}")
    linhas.append("="*50)
    linhas.append(f"Lances *{consultor}*\n")

    # Críticos prioritários: linhas inválidas
    if linhas_invalidas_idx or any(buckets_criticos.values()):
        linhas.append("Erros de Lances (Críticos):")
        if linhas_invalidas_idx:
            linhas.append("  Tipo: Linha inválida na entrada de cotas")
            for (n, texto) in linhas_invalidas_idx:
                linhas.append(f"    - Linha {n}: '{texto}'")
        for categoria, cotas in buckets_criticos.items():
            if cotas:
                linhas.append(f"  {categoria} ({len(cotas)} cota(s)):")
                for c in cotas:
                    linhas.append(f"    - {c}")
        linhas.append("")

    # Benignos
    if any(buckets_benignos.values()):
        linhas.append("Erros de Lances:")
        for categoria, cotas in buckets_benignos.items():
            if cotas:
                linhas.append(f"  {categoria} ({len(cotas)} cota(s)):")
                for c in cotas:
                    linhas.append(f"    - {c}")
        linhas.append("")

    # Resumo sem erros (quando aplicável)
    if not linhas_invalidas_idx and not any(buckets_benignos.values()) and not any(buckets_criticos.values()):
        linhas.append("Relatório de Execução - " + agora)
        linhas.append("="*50)
        linhas.append(f"Resumo para o consultor {consultor}:")
        linhas.append(f"  {resumo_sucesso} cotas totais do consultor {consultor}")
        linhas.append("  0 cotas com erros")

    conteudo = "\n".join(linhas) + "\n\n"
    try:
        with open(arquivo_saida, 'a', encoding='utf-8') as f:
            f.write(conteudo)
        logging.info(f"Relatório de erros gravado em: {arquivo_saida}")
    except Exception as e:
        logging.error(f"Falha ao gravar relatório de erros em '{arquivo_saida}': {e}")

def executar_verificacao_nomes(consultor):
    """Ponto de entrada para a verificação de nomes de arquivos a partir da GUI."""
    if not consultor:
        logging.error("Nome do consultor não fornecido para verificação.")
        return None
    logging.info(f"Disparando verificação de nomes para o consultor: {consultor}")
    consultor_path = os.path.join("Lances", consultor)
    return verificar_e_corrigir_nomes_pdf(consultor_path)


def main(consultor, cotas_input, stop_flag):
      """
      Função principal que orquestra a automação com retentativas de login e relatório.
      """
      summary = {
          "total_cotas": 0, "cotas_puladas": 0, "cotas_a_processar": 0,
          "sucesso": 0, "benigno": 0, "critico": 0
      }

      # Garante que a pasta do consultor e de downloads existam
      os.makedirs(os.path.join("Lances", consultor), exist_ok=True)
      os.makedirs(DOWNLOAD_DIR, exist_ok=True)

      cotas, linhas_invalidas, linhas_invalidas_idx = parse_lances_from_string(cotas_input)
      summary['total_cotas'] = len(cotas)
      if not cotas:
          logging.error("Nenhuma cota válida para processar.")
          # Flush aqui se não houver cotas para processar
          logging.getLogger().handlers[2].flush() # Força o flush dos logs para a GUI
          return summary

      # --- PRÉ-VERIFICAÇÃO DE COTAS ---
      logging.info("--- 🔎 INICIANDO PRÉ-VERIFICAÇÃO DE COTAS EXISTENTES... 🔎 ---")
      consultor_path = os.path.join("Lances", consultor)
      cotas_a_processar = []
      try:
          existing_pdfs = [f for f in os.listdir(consultor_path) if f.lower().endswith('.pdf') and f.upper().startswith("LANCE")]
          logging.info(f"Encontrados {len(existing_pdfs)} PDFs na pasta do consultor.")
          # Cache para evitar parsing repetido do mesmo nome de arquivo
          filename_cota_cache = {name: parse_cota_from_filename(name) for name in existing_pdfs}
      except FileNotFoundError:
          existing_pdfs = []
          filename_cota_cache = {}
          logging.warning(f"Pasta do consultor '{consultor_path}' não encontrada. Todas as cotas serão processadas como novas.")

      for cota_info in cotas:
          cota_tuple = (cota_info['grupo'], cota_info['cota'], cota_info['digito'])
          cota_encontrada = False
          for pdf_name, pdf_cota_tuple in filename_cota_cache.items():
              if pdf_cota_tuple and cota_tuple == pdf_cota_tuple:
                  logging.info(f"[PULANDO] Cota {cota_info['original']} já existe no arquivo: {pdf_name}")
                  summary['cotas_puladas'] += 1
                  cota_encontrada = True
                  break
          if not cota_encontrada:
              logging.info(f"[OK] Cota {cota_info['original']} é nova e será processada.")
              cotas_a_processar.append(cota_info)

      summary['cotas_a_processar'] = len(cotas_a_processar)
      logging.info(f"--- PRÉ-VERIFICAÇÃO FINALIZADA ---")
      logging.info(f"Resumo: {summary['total_cotas']} recebidas, {summary['cotas_puladas']} já existentes, {len(cotas_a_processar)} a processar.")
      # Flush aqui após o resumo da pré-verificação
      logging.getLogger().handlers[2].flush() # Força o flush dos logs para a GUI

      if not cotas_a_processar:
          logging.info("Nenhuma nova cota para processar após a pré-verificação.")
          # Este flush é redundante se o de cima funcionar, mas inofensivo.
          logging.getLogger().handlers[2].flush() # Força o flush dos logs para a GUI
          return summary

      driver = None
      # Buckets de erros para o relatório final
      buckets_benignos = defaultdict(list)
      buckets_criticos = defaultdict(list)
      login_sucesso = False
      max_tentativas_login = 3

      for tentativa in range(1, max_tentativas_login + 1):
          if stop_flag.is_set():
              logging.warning("Parada solicitada pelo usuário antes de iniciar o login.")
              return summary

          try:
              logging.info(f"--- Tentativa de Login #{tentativa}/{max_tentativas_login} ---")
              driver = get_driver()
              login(driver)
              login_sucesso = True
              logging.info("Login bem-sucedido. Prosseguindo com a automação.")
              break  # Sai do loop de tentativas se o login for bem-sucedido
          except InvalidCredentialsException as e:
              logging.warning(f"Credenciais inválidas (tentativa {tentativa}/{max_tentativas_login}). Repetindo login...")
              if driver:
                  try:
                      driver.quit()
                  except Exception:
                      pass
              time.sleep(2)
          except CaptchaDetectedException as e:
              logging.warning(f"{e} - Tentativa {tentativa} falhou. Reiniciando o navegador em 5 segundos...")
              if driver:
                  driver.quit()
              time.sleep(5)
          except Exception as e:
              logging.critical(f"Erro fatal inesperado durante a configuração ou login: {e}", exc_info=True)
              if driver:
                  driver.quit()
              # Interrompe as tentativas em caso de erro grave não relacionado a CAPTCHA
              break

      if not login_sucesso:
          logging.critical("="*60)
          logging.critical("ERRO CRÍTICO: A automação não pôde iniciar após múltiplas tentativas.")
          logging.critical("Um CAPTCHA pode estar bloqueando o acesso ou ocorreu um erro de configuração.")
          logging.critical("Por favor, verifique sua conexão e as configurações no arquivo .env.")
          logging.critical("Se o problema for CAPTCHA, resolva-o manualmente no perfil do Firefox.")
          logging.critical("="*60)
          summary['critico'] = len(cotas_a_processar) # Marca todas como falha se o login falhar
          return summary

      # Lógica de automação principal
      try:
          for cota_info in cotas_a_processar: # Iterar sobre a lista filtrada
              if stop_flag.is_set():
                  logging.info("Parada solicitada pelo usuário. Encerrando o processamento de cotas.")
                  break

              status, mensagem = run_automation_for_cota(driver, cota_info, consultor)
              logging.info(f"Resultado para {cota_info['original']}: {status} - {mensagem}")

              if status == 'SUCESSO':
                  summary['sucesso'] += 1
              elif status == 'ERRO_BENIGNO':
                  summary['benigno'] += 1
                  categoria = _classificar_benigno(mensagem)
                  buckets_benignos[categoria].append(cota_info['original'])
              else:  # ERRO_CRITICO
                  summary['critico'] += 1
                  categoria = _classificar_critico(mensagem)
                  buckets_criticos[categoria].append(cota_info['original'])

              if status != 'SUCESSO':
                  logging.warning(f"Status não foi SUCESSO ({status}). Retornando à página inicial para garantir um estado limpo.")
                  try:
                      click_element(driver, *ServopaLocators.HOME_LOGO_LINK)
                      remover_loading(driver)
                      # Confirma que voltou para um estado conhecido
                      WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Ferramentas Admin')] ")))
                      logging.info("Retorno à página inicial realizado com sucesso.")
                  except Exception as nav_e:
                      logging.error(f"Falha crítica ao tentar retornar à página inicial: {nav_e}. A automação pode se tornar instável.")

          # Verificação automática final de nomes
          logging.info("--- VERIFICAÇÃO AUTOMÁTICA DE NOMES DE ARQUIVOS ---")
          verificar_e_corrigir_nomes_pdf(consultor_path) # Usar o consultor_path definido anteriormente

      except InvalidSessionIdException as e:
          logging.error(f"Sessão do navegador perdida: {e}. A automação será encerrada.")
          remaining_cotas = len(cotas_a_processar) - (summary['sucesso'] + summary['benigno'] + summary['critico'])
          summary['critico'] += remaining_cotas
      except Exception as e:
          logging.error(f"Erro crítico na execução principal: {e}", exc_info=True)
          remaining_cotas = len(cotas_a_processar) - (summary['sucesso'] + summary['benigno'] + summary['critico'])
          summary['critico'] += remaining_cotas
      finally:
          if driver:
              try:
                  driver.quit()
              except InvalidSessionIdException:
                  logging.warning("A sessão do driver já estava inválida ao tentar sair.")
                  pass
          # Escreve o relatório final de erros
          try:
              _escrever_relatorio_erros(
                  consultor=consultor,
                  linhas_invalidas_idx=linhas_invalidas_idx,
                  buckets_benignos=buckets_benignos,
                  buckets_criticos=buckets_criticos,
                  resumo_sucesso=summary['total_cotas'],
                  arquivo_saida=ERROS_FILE,
              )
          except Exception as e:
              logging.error(f"Falha ao gerar o relatório de erros: {e}")
          logging.info(f"Automação finalizada. Retornando resumo: {summary}")
          return summary

if __name__ == "__main__":
    # Exemplo de como testar a função main diretamente
    class MockStopFlag:
        def is_set(self): return False

    main(consultor="Teste", cotas_input="1564,221,1", stop_flag=MockStopFlag())
