import os
import time
import shutil
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, InvalidSessionIdException, ElementClickInterceptedException
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile # Importa FirefoxProfile
from dotenv import load_dotenv
import re
from pypdf import PdfReader

class CaptchaDetectedException(Exception):
    """Exceção customizada para quando um CAPTCHA é detectado."""
    pass

# Carrega as variáveis de ambiente do arquivo .env
# Garante que FIREFOX_BINARY_PATH não está pré-definido no ambiente, forçando a leitura do .env
if 'FIREFOX_BINARY_PATH' in os.environ:
    del os.environ['FIREFOX_BINARY_PATH']
load_dotenv()

# --- Configurações Carregadas do .env ---
GECKODRIVER_PATH = os.getenv("GECKODRIVER_PATH")
FIREFOX_BINARY_PATH = os.getenv("FIREFOX_BINARY_PATH")
SERVOPA_URL = os.getenv("SERVOPA_URL")
CPF_CNPJ = os.getenv("CPF_CNPJ")
SENHA = os.getenv("SENHA")
LANCE_LIVRE_PERCENTUAL = os.getenv("LANCE_LIVRE_PERCENTUAL")
LANCE_LIVRE_DESCONTAR_CARTA = os.getenv("LANCE_LIVRE_DESCONTAR_CARTA")
ERROS_FILE = os.getenv("ERROS_FILE")
LANCES_FILE = os.getenv("LANCES_FILE", "lances.txt") # Adiciona o arquivo de lances
FIREFOX_PROFILE_PATH = r"C:\Users\gabri\AppData\Roaming\Mozilla\Firefox\Profiles\oj00n9wt.seleniumProfile" # Caminho do perfil do Firefox

error_log_buffer = {}

def registrar_erro(log_file, error_type, cota_info, mensagem, consultor="Automação Lances"):
    """Registra uma mensagem de erro no buffer para o relatório final."""
    global error_log_buffer

    if consultor not in error_log_buffer:
        error_log_buffer[consultor] = {"cotas": {}, "geral": {}}

    # Erros específicos de cotas
    if cota_info and all(k in cota_info for k in ['grupo', 'cota', 'digito']):
        if error_type not in error_log_buffer[consultor]["cotas"]:
            error_log_buffer[consultor]["cotas"][error_type] = []
        
        cota_str = f"{cota_info['grupo']},{cota_info['cota']},{cota_info['digito']}"
        if cota_str not in error_log_buffer[consultor]["cotas"][error_type]:
            error_log_buffer[consultor]["cotas"][error_type].append(cota_str)
        print(f"[ERRO - {consultor} - {error_type}] Cota {cota_str}: {mensagem}")
    # Erros gerais (críticos)
    else:
        if error_type not in error_log_buffer[consultor]["geral"]:
            error_log_buffer[consultor]["geral"][error_type] = []
        
        if mensagem not in error_log_buffer[consultor]["geral"][error_type]:
            error_log_buffer[consultor]["geral"][error_type].append(mensagem)
        print(f"[ERRO CRÍTICO - {consultor} - {error_type}]: {mensagem}")


def flush_error_log_buffer(log_file, total_cotas_processadas, consultor_name):
    """Adiciona um novo bloco de relatório de erros ao final do arquivo de log existente e gera o resumo."""
    global error_log_buffer

    if consultor_name not in error_log_buffer or not (error_log_buffer[consultor_name]["cotas"] or error_log_buffer[consultor_name]["geral"]):
        print(f"Nenhum erro registrado para o consultor {consultor_name}.")
        if total_cotas_processadas > 0:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{ '=' * 50}\n")
                f.write(f"Relatório de Execução - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{ '=' * 50}\n")
                f.write(f"Resumo para o consultor {consultor_name}:\n")
                f.write(f"  {total_cotas_processadas} cotas totais do consultor {consultor_name}\n")
                f.write(f"  0 cotas com erros\n\n")
            print(f"Relatório de execução (sem erros) foi ADICIONADO em: {log_file}")
        error_log_buffer.pop(consultor_name, None)
        return

    consultor_erros = error_log_buffer.get(consultor_name, {})
    erros_cotas = consultor_erros.get("cotas", {})
    erros_gerais = consultor_erros.get("geral", {})

    total_cotas_com_erro = sum(len(set(cotas)) for cotas in erros_cotas.values())
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{ '=' * 50}\n")
        f.write(f"Relatório de Erros da Execução - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{ '=' * 50}\n")
        
        f.write(f"Lances *{consultor_name}*\n\n")

        if erros_gerais:
            f.write("Erros de Lances (Críticos):\n")
            for error_type, mensagens in sorted(erros_gerais.items()):
                f.write(f"  Tipo: {error_type}\n")
                for msg in sorted(list(set(mensagens))):
                    f.write(f"    - {msg}\n")
            f.write("\n")

        if erros_cotas:
            f.write("Erros de Lances:\n")
            for error_type, cotas in sorted(erros_cotas.items()):
                f.write(f"  {error_type} ({len(set(cotas))} cota(s)):\n")
                for cota in sorted(list(set(cotas))):
                    f.write(f"    - {cota}\n")
            f.write("\n")
            
    print(f"Novo relatório de erros foi ADICIONADO em: {log_file}")
    error_log_buffer.pop(consultor_name, None)


def criar_pastas(consultor):
    """Cria as pastas necessárias para o download e armazenamento dos PDFs."""
    download_path = os.path.abspath("downloads_temporarios")
    consultor_path = os.path.abspath(f"Lances/{consultor}")
    os.makedirs(download_path, exist_ok=True)
    os.makedirs(consultor_path, exist_ok=True)
    for filename in os.listdir(download_path):
        file_path = os.path.join(download_path, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    return download_path, consultor_path

def configurar_firefox(download_path, firefox_binary_path, profile_path):
    """Configura e retorna as opções do Firefox para automação."""
    options = Options()
    options.binary_location = firefox_binary_path
    options.profile = FirefoxProfile(profile_path) # Carrega o perfil existente
    
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", download_path)
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf")
    options.set_preference("pdfjs.disabled", True)
    options.set_preference("gfx.downloadable_fonts.enabled", False) # Desabilita o download de fontes
    # Desabilita as políticas mais rigorosas de SameSite para cookies
    options.set_preference("network.cookie.sameSite.laxByDefault", False)
    options.set_preference("network.cookie.sameSite.noneRequiresSecure", False)
    return options

def remover_loading(driver):
    """Remove o overlay 'pace-active' de forma direta e aguarda um instante."""
    # A remoção via JS é mais direta e menos propensa a loops infinitos.
    print("Removendo tela de loading ('pace-active')...")
    driver.execute_script("document.querySelector('.pace-active')?.remove();")
    time.sleep(0.4) # Pequena pausa para a UI atualizar

def sanitizar_nome_arquivo(nome):
    """Remove caracteres inválidos de um nome de arquivo para compatibilidade com o Windows."""
    invalid_chars = '\/:*?"<>|'
    nome_sanitizado = nome
    for char in invalid_chars:
        nome_sanitizado = nome_sanitizado.replace(char, '_') # Substitui por underscore
    return nome_sanitizado


def aguardar_download_concluir(download_path, timeout=90):
    """Aguarda a conclusão do download de um arquivo PDF de forma mais robusta."""
    print("\n--- Verificação de Download ---")
    print(f"Monitorando a pasta: {download_path}")
    start_time = time.time()
    last_size = -1
    stable_time = 0

    while time.time() - start_time < timeout:
        # Procura por arquivos PDF que não sejam temporários
        files = [f for f in os.listdir(download_path) if f.endswith(".pdf") and not f.endswith(".part")]
        
        if files:
            file_path = os.path.join(download_path, files[0])
            print(f"  - Arquivo PDF encontrado: {files[0]}")
            
            # Verifica se o tamanho do arquivo está estável
            current_size = os.path.getsize(file_path)
            print(f"  - Verificando tamanho: {current_size} bytes")

            if current_size == last_size and current_size > 0:
                stable_time += 1
                print(f"  - Tamanho do arquivo estável (contagem: {stable_time})")
                if stable_time >= 3: # Considera estável após 3 verificações (aprox. 3 segundos)
                    print(f"Download concluído e estável: {files[0]}")
                    print("-----------------------------")
                    return files[0]
            else:
                stable_time = 0 # Reseta a contagem se o tamanho mudar
            
            last_size = current_size
        else:
            print("Aguardando a criação do arquivo PDF...")

        time.sleep(1)

    raise TimeoutException("Tempo esgotado esperando pelo download do PDF.")

def check_for_captcha(driver):
    """Verifica a presença de CAPTCHA usando uma espera explícita e lança uma exceção se encontrado."""
    print("Verificando a presença de CAPTCHA...")
    try:
        # Espera por até 5 segundos pelo elemento que contém o texto do CAPTCHA.
        # Isso evita falsos negativos se a página ainda estiver carregando.
        wait = WebDriverWait(driver, 5)
        wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Confirme que é humano')]" )))
        
        # Se o elemento foi encontrado, lança a exceção para acionar a retentativa.
        print("CAPTCHA (Texto 'Confirme que é humano') detectado!")
        raise CaptchaDetectedException("CAPTCHA com texto 'Confirme que é humano' detectado.")

    except TimeoutException:
        # Se o elemento não apareceu em 5 segundos, consideramos que não há CAPTCHA.
        print("Nenhum CAPTCHA detectado.")
        pass # Continua a execução normal

def clicar_com_retentativa(driver, by, value, cota_info, consultor_name, timeout=5):
    """Tenta clicar em um elemento com uma retentativa em caso de falha inicial."""
    try:
        elemento = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        driver.execute_script("arguments[0].click();", elemento)
        return True
    except (ElementClickInterceptedException, TimeoutException) as e:
        print(f"Primeira tentativa de clique falhou: {e.__class__.__name__}. Tentando novamente em 1 segundo...")
        time.sleep(1)
        try:
            elemento = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
            driver.execute_script("arguments[0].click();", elemento)
            return True
        except (ElementClickInterceptedException, TimeoutException, NoSuchElementException) as final_e:
            erro_msg = f"Falha ao clicar no elemento '{value}' após retentativa: {final_e.__class__.__name__}"
            print(f"[ERRO GRAVE] {erro_msg}")
            registrar_erro(ERROS_FILE, "Erro de Clique", cota_info, erro_msg, consultor_name)
            debug_path = os.path.join(os.path.abspath(f"Lances/{consultor_name}"), f"ERRO-CLIQUE-{cota_info['grupo']}-{cota_info['cota']}.png")
            try:
                driver.save_screenshot(debug_path)
                print(f"---> Screenshot de depuração de clique salvo em: {debug_path}")
            except Exception as dbg_e:
                print(f"[ALERTA] Não foi possível salvar o screenshot de depuração: {dbg_e}")
            return False

def navegar_e_buscar_cota(driver, wait, cota_info, consultor_name):
    """Navega até a busca e procura pela cota de forma eficiente."""
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']
    print(f"Navegando: Ferramentas Admin -> Buscar para a cota {grupo}/{cota}-{digito}")

    remover_loading(driver)
    time.sleep(0.5)

    print("Abrindo o menu 'Ferramentas Admin'...")
    if not clicar_com_retentativa(driver, By.XPATH, "//a[contains(., 'Ferramentas Admin')]", cota_info, consultor_name):
        return False # Falha crítica, interrompe a navegação para esta cota

    remover_loading(driver)
    time.sleep(0.5)

    print("Clicando em 'Buscar'...")
    buscar_element = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@href='https://www.consorcioservopa.com.br/vendas/buscar']")))
    driver.execute_script("arguments[0].click();", buscar_element)

    remover_loading(driver)
    time.sleep(0.5)
    print("Preenchendo formulário de busca...")

    wait.until(EC.presence_of_element_located((By.ID, "grupo"))).send_keys(grupo)
    wait.until(EC.presence_of_element_located((By.ID, "plano"))).send_keys(cota)
    wait.until(EC.presence_of_element_located((By.ID, "digito"))).send_keys(digito)
    
    remover_loading(driver)
    time.sleep(0.5)

    btn_busca = wait.until(EC.element_to_be_clickable((By.ID, "btn_busca_usuario")))
    driver.execute_script("arguments[0].click();", btn_busca)
    
    remover_loading(driver)
    return True

def realizar_lance(driver, wait, cota_info, lance_config, consultor_name, download_path, consultor_path):
    """Processa o lance para uma cota, incluindo todas as verificações e o download do PDF."""
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']

    print("Acessando a área de lances...")
    remover_loading(driver)
    lances_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/vendas/lances')] ")))
    driver.execute_script("arguments[0].scrollIntoView(true);", lances_button)
    driver.execute_script("arguments[0].click();", lances_button)
    remover_loading(driver)

    # Verificações de erros comuns (Contemplada, Fidelidade, etc.)
    try:
        error_message_xpath = "//div[contains(@class, 'message-block') and contains(@class, 'error') and contains(., 'Cota já está contemplada')]"
        WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.XPATH, error_message_xpath)))
        registrar_erro(ERROS_FILE, "Cota Contemplada", cota_info, "A cota já foi contemplada.", consultor_name)
        return "Cota Contemplada"
    except TimeoutException:
        pass # OK

    if driver.find_elements(By.XPATH, "//div[@class='tab-switcher']//a[text()='Fidelidade']"):
        registrar_erro(ERROS_FILE, "Lance Fidelidade", cota_info, "A cota possui Lance Fidelidade.", consultor_name)
        return "Lance Fidelidade"

    # Nova lógica para tratar Lance Fixo e Livre
    try:
        # Procura pela aba "Fixo". Se existir, clica nela e prossegue.
        lance_fixo_tab = driver.find_element(By.XPATH, "//div[@class='tab-switcher']//a[text()='Fixo']")
        print("Detectado: Lance Fixo. Prosseguindo sem preencher valores.")
        driver.execute_script("arguments[0].click();", lance_fixo_tab)
        time.sleep(1) # Pausa para a aba carregar

    except NoSuchElementException:
        # Se a aba "Fixo" não for encontrada, assume-se Lance Livre.
        print("Detectado: Lance Livre. Preenchendo formulário.")
        try:
            remover_loading(driver)
            time.sleep(1)
            
            print("Preenchendo percentual do lance...")
            lance_percentual_input = wait.until(EC.visibility_of_element_located((By.ID, "tx_Lanliv")))
            driver.execute_script("arguments[0].value = arguments[1];", lance_percentual_input, lance_config['percentual'])
            time.sleep(0.5)

            print("Preenchendo valor a descontar da carta...")
            lance_descontar_input = wait.until(EC.visibility_of_element_located((By.ID, "tx_lanliv_emb")))
            driver.execute_script("arguments[0].value = arguments[1];", lance_descontar_input, lance_config['descontar_carta'])
            time.sleep(0.5)

        except TimeoutException as e:
            registrar_erro(ERROS_FILE, "Falha Preenchimento Lance", cota_info, f"Não foi possível preencher o formulário de Lance Livre: {e}", consultor_name)
            return "Falha Preenchimento Lance"

    print("Clicando em 'Simular'...")
    driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.ID, "btn_simular"))))
    remover_loading(driver)

    try:
        WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.ID, "num_protocolo_ant")))
        registrar_erro(ERROS_FILE, "Requer Protocolo", cota_info, "Lance já realizado (protocolo encontrado).", consultor_name)
        return "Requer Protocolo"
    except TimeoutException:
        pass # OK

    # Extração do nome e registro do PDF
    nome_cliente_completo = "NOME_NAO_ENCONTRADO"
    try:
        nome_cliente_element = wait.until(EC.presence_of_element_located((By.XPATH, "//span[text()='Consorciado']/following-sibling::h3[1]")))
        nome_cliente_completo = nome_cliente_element.text.strip()
    except (TimeoutException, NoSuchElementException):
        print("ALERTA: Não foi possível extrair o nome completo do cliente.")

    print("Clicando em 'Registrar' para gerar o PDF...")
    driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Registrar"))))

    pdf_filename = aguardar_download_concluir(download_path)
    nome_cliente_sanitizado = sanitizar_nome_arquivo(nome_cliente_completo)
    novo_nome = f"LANCE- {nome_cliente_sanitizado} {grupo}.{cota}-{digito}.pdf"
    shutil.move(os.path.join(download_path, pdf_filename), os.path.join(consultor_path, novo_nome))
    print(f"PDF salvo como: {os.path.join(consultor_path, novo_nome)}")

    return True

def verificar_status_cota(driver, wait, cota_info, consultor_name):
    """Verifica o status da cota (Ativa, Cancelada, etc.) e retorna o nome do cliente se ativa."""
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']
    
    print("Procurando pela cota 'ATIVA' nos resultados da busca...")
    try:
        result_body = wait.until(EC.presence_of_element_located((By.XPATH, "//tbody")))
        rows = result_body.find_elements(By.XPATH, ".//tr[@onclick]")
        if not rows:
            raise TimeoutException("Tabela de resultados vazia.")

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 8 and cells[7].text.strip().upper() == "ATIVO":
                nome_cliente = cells[3].text.strip()
                print(f"Cota ATIVA encontrada para o cliente: {nome_cliente}")
                driver.execute_script("arguments[0].click();", row)
                remover_loading(driver)
                
                # Segunda verificação: "Extrato - Cancelado"
                try:
                    h2_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//section[@class='main-view']//h2")))
                    if "Extrato - Cancelado" in h2_element.text:
                        print(f"ERRO: Detectado 'Extrato - Cancelado' para a cota {grupo}/{cota}-{digito}.")
                        registrar_erro(ERROS_FILE, "Extrato - Cancelado", cota_info, "Página de extrato cancelado detectada.", consultor_name)
                        return None, "Extrato - Cancelado"
                except TimeoutException:
                    pass # Se não encontrar o H2, a cota está OK.

                return nome_cliente, "Ativa"

        print(f"ERRO: Nenhuma cota com status 'ATIVO' foi encontrada para {grupo}/{cota}-{digito}.")
        registrar_erro(ERROS_FILE, "Cota Não Ativa", cota_info, "Nenhuma cota 'ATIVA' encontrada.", consultor_name)
        return None, "Não Ativa"

    except TimeoutException:
        registrar_erro(ERROS_FILE, "Cota Não Existe", cota_info, "Tabela de resultados não apareceu.", consultor_name)
        return None, "Não Existe"

def run_automation(driver, wait, cota_info, download_path, consultor_path, lance_config, consultor_name):
    """
    Executa o fluxo de automação para uma única cota.
    Retorna True em caso de sucesso, False em caso de falha.
    """
    grupo, cota, digito = cota_info['grupo'], cota_info['cota'], cota_info['digito']
    print(f"\n{'='*20} INICIANDO COTA {grupo}/{cota}-{digito} {'='*20}")

    try:
        if not navegar_e_buscar_cota(driver, wait, cota_info, consultor_name):
            return "Falha Navegação"

        _, status_cota = verificar_status_cota(driver, wait, cota_info, consultor_name)

        if status_cota != "Ativa":
            return status_cota

        resultado_lance = realizar_lance(driver, wait, cota_info, lance_config, consultor_name, download_path, consultor_path)


        if resultado_lance is True:
            print("**************************************************")
            print(f"* SUCESSO: Lance para a cota {grupo}/{cota}-{digito} registrado!")
            print("**************************************************")
        else:
            print(f"ERRO: O lance falhou com o status: {resultado_lance}")

        return resultado_lance

    except (TimeoutException, NoSuchElementException, Exception) as e:
        error_type = e.__class__.__name__
        erro_msg = str(e).splitlines()[0]
        print(f"[ERRO GRAVE - {error_type}] Cota {grupo}/{cota}-{digito}: {erro_msg}")
        registrar_erro(ERROS_FILE, error_type, cota_info, erro_msg, consultor_name)
        
        debug_path = os.path.join(consultor_path, f"ERRO-{grupo}-{cota}-{digito}.png")
        try:
            driver.save_screenshot(debug_path)
            print(f"---> Screenshot de depuração salvo em: {debug_path}")
        except Exception as dbg_e:
            print(f"[ALERTA] Não foi possível salvar os arquivos de depuração: {dbg_e}")
        
        return "Erro Inesperado"
        # A recuperação agora é feita no loop principal em main()

# --- Funções de Verificação e Correção de Nomes de PDF ---

def extrair_info_pdf(caminho_pdf):
    """Extrai nome e cota de um arquivo PDF de forma robusta."""
    try:
        reader = PdfReader(caminho_pdf)
        if not reader.pages:
            return None, None, "PDF corrompido ou sem páginas"
        
        texto = "".join(page.extract_text() or "" for page in reader.pages)
        texto_limpo = re.sub(r'\s+', ' ', texto).strip()

        # Padrão para encontrar o nome do consorciado (geralmente em maiúsculas)
        nome_match = re.search(r"Consorciado\s*[:\-]?\s*([A-ZÀ-Ú\s]{5,})", texto_limpo, re.IGNORECASE)
        nome = nome_match.group(1).strip() if nome_match else None

        # Padrão para encontrar a cota no formato GRUPO/COTA-DIGITO
        cota_match = re.search(r"(\d{4}[\./]?\d{1,4}-\d)", texto_limpo)
        cota = cota_match.group(1).strip() if cota_match else None

        if not nome or not cota:
            return None, None, f"Nome ({'OK' if nome else 'FALHA'}) ou Cota ({'OK' if cota else 'FALHA'}) não encontrados."

        return nome, cota, None

    except Exception as e:
        return None, None, f"Erro de leitura do PDF: {e}"

def normalizar_nome(nome):
    """Padroniza o nome para consistência."""
    return re.sub(r'\s+', ' ', nome).strip().upper()

def normalizar_cota(cota_raw):
    """Padroniza a cota para o formato GRUPO.COTA-DIGITO."""
    if not cota_raw: return ""
    return cota_raw.replace('/', '.').replace(',', '.')

def verificar_e_corrigir_nomes_pdf(consultor_path, log_correcoes_path):
    """Verifica e corrige os nomes dos arquivos PDF em uma pasta específica."""
    print(f"\n--- Verificando nomes de arquivos em: {consultor_path} ---")
    correcoes = []

    for nome_arquivo in os.listdir(consultor_path):
        if not nome_arquivo.lower().endswith(".pdf") or not nome_arquivo.upper().startswith("LANCE-"):
            continue

        caminho_completo = os.path.join(consultor_path, nome_arquivo)
        nome_pdf, cota_pdf, erro = extrair_info_pdf(caminho_completo)

        if erro:
            msg = f"  - ERRO ao ler '{nome_arquivo}': {erro}"
            print(msg)
            correcoes.append(msg)
            continue

        nome_pdf_norm = normalizar_nome(nome_pdf)
        cota_pdf_norm = normalizar_cota(cota_pdf)
        nome_pdf_sanitizado = sanitizar_nome_arquivo(nome_pdf_norm)

        novo_nome_arquivo = f"LANCE- {nome_pdf_sanitizado} {cota_pdf_norm}.pdf"
        
        if nome_arquivo != novo_nome_arquivo:
            novo_caminho_completo = os.path.join(consultor_path, novo_nome_arquivo)
            try:
                os.rename(caminho_completo, novo_caminho_completo)
                msg = f"  - CORRIGIDO: '{nome_arquivo}' -> '{novo_nome_arquivo}'"
                print(msg)
                correcoes.append(msg)
            except OSError as e:
                msg = f"  - FALHA AO RENOMEAR '{nome_arquivo}': {e}"
                print(msg)
                correcoes.append(msg)

    if correcoes:
        with open(log_correcoes_path, "a", encoding="utf-8") as f:
            f.write(f"\n{ '=' * 50}\n")
            f.write(f"Relatório de Correções - {time.strftime('%Y-%m-%d %H:%M:%S')} - {os.path.basename(consultor_path)}\n")
            f.write(f"{ '=' * 50}\n")
            for linha in correcoes:
                f.write(f"{linha}\n")
        print(f"Relatório de correções salvo em: {log_correcoes_path}")
    else:
        print("Nenhuma correção de nome de arquivo foi necessária.")

def fazer_login(driver, wait):
    """Realiza o login no sistema, com tratamento de exceção priorizado para CAPTCHA."""
    print("Acessando o site...")
    driver.get(SERVOPA_URL)
    
    # Garante que a tela de loading seja removida ANTES de qualquer verificação.
    remover_loading(driver)

    # A verificação de CAPTCHA é feita após remover o loading, para garantir que a página esteja visível.
    # Se encontrar, lança a exceção que o loop `main` irá tratar.
    check_for_captcha(driver)

    # Se não houver CAPTCHA, o script continua para o login.
    print("Nenhum CAPTCHA detectado. Prosseguindo com o login...")

    try:
        print("Preenchendo CPF/CNPJ...")
        cpf_cnpj_input = wait.until(EC.element_to_be_clickable((By.ID, "representante_cpf_cnpj")))
        driver.execute_script("arguments[0].value = arguments[1];", cpf_cnpj_input, CPF_CNPJ)
        time.sleep(0.5)

        print("Preenchendo a senha...")
        senha_input = wait.until(EC.element_to_be_clickable((By.ID, "representante_senha")))
        senha_input.send_keys(SENHA)

        login_button = wait.until(EC.element_to_be_clickable((By.ID, "btn_representante")))
        driver.execute_script("arguments[0].click();", login_button)

        print("Aguardando resultado do login...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Ferramentas Admin')]" )))
        
        print("Login realizado com sucesso!")
        remover_loading(driver)

    except (TimeoutException, NoSuchElementException) as e:
        # Se o login falhar por qualquer motivo, a primeira suspeita é um CAPTCHA tardio.
        print("Falha no processo de login. Verificando novamente por um CAPTCHA tardio...")
        check_for_captcha(driver)

        # Se `check_for_captcha` não lançou exceção, o erro é outro.
        print("Nenhum CAPTCHA tardio encontrado. O erro é outro.")
        try:
            error_element = driver.find_element(By.XPATH, "//div[@class='error' and contains(text(), 'CPF/CNPJ ou senha inválidos!')]")
            if error_element:
                raise Exception("Login falhou: CPF/CNPJ ou senha inválidos!")
        except NoSuchElementException:
            debug_path = os.path.join(os.path.abspath("downloads_temporarios"), "login_fail_screenshot.png")
            try:
                driver.save_screenshot(debug_path)
                print(f"Screenshot de depuração do erro de login salvo em: {debug_path}")
            except Exception as dbg_e:
                print(f"[ALERTA] Não foi possível salvar o screenshot de depuração do login: {dbg_e}")
            raise Exception(f"Falha crítica no login. A página pode não ter carregado corretamente ou um elemento não foi encontrado. Erro: {e}")

def main(consultor_name="Automação Lances", update_callback=None, stop_flag=None):
    """Função principal que orquestra todo o processo de automação com retentativas para CAPTCHA."""
    if not all([GECKODRIVER_PATH, SERVOPA_URL, CPF_CNPJ, SENHA]):
        print("ERRO: Variáveis de ambiente essenciais não estão definidas no .env.")
        if update_callback: update_callback("error")
        return

    try:
        with open(LANCES_FILE, 'r', encoding='utf-8') as f:
            cotas_para_processar = [
                {'grupo': p[0].strip(), 'cota': p[1].strip(), 'digito': p[2].strip()}
                for line in f if (p := line.strip().split(',')) and len(p) == 3 and not line.startswith('#')
            ]
        if not cotas_para_processar:
            print(f"Nenhuma cota encontrada no arquivo {LANCES_FILE} para processar.")
            return
        print(f"Encontradas {len(cotas_para_processar)} cotas para processar.")
    except FileNotFoundError:
        registrar_erro(ERROS_FILE, "Erro Crítico", {}, f"Arquivo de lances '{LANCES_FILE}' não encontrado.", consultor_name)
        return
    except Exception as e:
        registrar_erro(ERROS_FILE, "Erro Crítico", {}, f"Erro ao ler o arquivo de lances: {e}", consultor_name)
        return

    driver = None
    login_sucesso = False
    max_tentativas_login = 3
    total_cotas_processadas = 0

    for tentativa in range(1, max_tentativas_login + 1):
        try:
            print(f"\n--- Tentativa de Login #{tentativa}/{max_tentativas_login} ---")
            firefox_binary_path = os.getenv("FIREFOX_BINARY_PATH")
            if not firefox_binary_path or not os.path.exists(firefox_binary_path):
                raise FileNotFoundError(f"Caminho para o Firefox em FIREFOX_BINARY_PATH não é válido: '{firefox_binary_path}'")

            geckodriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers", "geckodriver.exe")
            if not os.path.exists(geckodriver_path):
                raise FileNotFoundError(f"Geckodriver não encontrado em '{geckodriver_path}'")

            options = configurar_firefox(os.path.abspath("downloads_temporarios"), firefox_binary_path, FIREFOX_PROFILE_PATH)
            service = Service(executable_path=geckodriver_path)
            driver = webdriver.Firefox(service=service, options=options)
            wait = WebDriverWait(driver, 20)

            fazer_login(driver, wait)
            login_sucesso = True
            break # Se o login for bem-sucedido, sai do loop de tentativas

        except CaptchaDetectedException as e:
            print(f"[ALERTA] {e} - Tentativa {tentativa} falhou. Reiniciando o navegador...")
            if driver:
                driver.quit()
            time.sleep(5) # Pausa antes de tentar novamente
        
        except Exception as e:
            error_msg = f"Ocorreu um erro fatal durante o login: {e.__class__.__name__}: {e}"
            print(error_msg)
            registrar_erro(ERROS_FILE, "Erro Crítico de Login", {}, error_msg, consultor_name)
            if driver:
                driver.quit()
            break # Sai do loop em caso de outros erros fatais

    if not login_sucesso:
        print("\n" + "!" * 60)
        print("ERRO CRÍTICO: A automação não pôde iniciar após múltiplas tentativas.")
        print("Um CAPTCHA está bloqueando o acesso.")
        print("\n** AÇÃO NECESSÁRIA **")
        print("1. Feche este programa.")
        print(f"2. Abra o Firefox manualmente usando o perfil: {FIREFOX_PROFILE_PATH}")
        print("3. Acesse o site da Servopa: https://www.consorcioservopa.com.br/vendas")
        print("4. Faça o login e resolva o CAPTCHA (marcando a caixa 'não sou um robô').")
        print("5. Após o login bem-sucedido, feche o Firefox e execute a automação novamente.")
        print("!" * 60)
        registrar_erro(ERROS_FILE, "Bloqueio por CAPTCHA", {}, "Todas as tentativas de login falharam devido a um CAPTCHA persistente.", consultor_name)
        return

    # Se o login foi bem-sucedido, continua com a automação
    try:
        lance_config = {'percentual': LANCE_LIVRE_PERCENTUAL, 'descontar_carta': LANCE_LIVRE_DESCONTAR_CARTA}
        download_path, consultor_path = criar_pastas(consultor_name)

        for cota_info in cotas_para_processar:
            if stop_flag and stop_flag.is_set():
                print("Parada solicitada. Encerrando o loop de cotas.")
                break
            total_cotas_processadas += 1
            status_automacao = run_automation(driver, wait, cota_info, download_path, consultor_path, lance_config, consultor_name)
            
            if update_callback:
                status = "success" if status_automacao is True else "error"
                update_callback(status)
            
            print(f"{'='*20} FIM DA COTA {cota_info['grupo']}/{cota_info['cota']}-{cota_info['digito']} | STATUS: {status_automacao} {'='*20}")

            if status_automacao is not True:
                print(f"Retornando à página inicial para a próxima cota após status: {status_automacao}")
                try:
                    logo_image = wait.until(EC.element_to_be_clickable((By.XPATH, "//aside[@id='main-nav']//img[@alt='Consórcio Servopa']")))
                    driver.execute_script("arguments[0].click();", logo_image)
                    remover_loading(driver)
                    wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Ferramentas Admin')]" )))
                except Exception as nav_e:
                    print(f"Falha ao retornar à página inicial. Tentando recarregar a URL. Erro: {nav_e}")
                    driver.get(SERVOPA_URL)
                    wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Ferramentas Admin')]" )))

    except (InvalidSessionIdException, Exception) as e:
        error_msg = f"Ocorreu um erro fatal na automação: {e.__class__.__name__}: {e}"
        print(error_msg)
        registrar_erro(ERROS_FILE, "Erro Crítico", {}, error_msg, consultor_name)
    finally:
        if driver:
            # Chama a verificação de nomes antes de fechar
            if login_sucesso and total_cotas_processadas > 0:
                log_correcoes_path = os.path.abspath("correcoes_nomes.txt")
                verificar_e_corrigir_nomes_pdf(consultor_path, log_correcoes_path)

            print("Fechando o navegador.")
            driver.quit()
        flush_error_log_buffer(ERROS_FILE, total_cotas_processadas, consultor_name)
        print("\n--- Automação finalizada. ---")


if __name__ == "__main__":
    main()