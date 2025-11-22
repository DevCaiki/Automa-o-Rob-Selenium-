from selenium.webdriver.common.by import By

"""
Este arquivo foi completamente reestruturado em 08/09/2025 para corrigir uma
incompatibilidade de arquitetura com 'automacao_servopa.py'.

O script de automação espera que os localizadores estejam organizados em classes
e sejam tuplas (ex: (By.ID, 'meu-id')), enquanto a versão anterior deste arquivo
usava variáveis globais com strings simples.

Esta nova versão implementa a estrutura de classes correta.
- Localizadores existentes foram mapeados para os nomes esperados pelo script.
- Localizadores que estavam faltando foram adicionados como 'chutes' (suposições
  educadas) e podem precisar de ajuste após testes no site real.
"""

class ServopaLocators:
    """Localizadores para login e elementos gerais do site."""
    # Mapeado de 'LOGIN_CPF_CNPJ_ID' da versão anterior.
    USERNAME_FIELD = (By.ID, "representante_cpf_cnpj") 
    
    # Mapeado de 'LOGIN_SENHA_ID' da versão anterior.
    PASSWORD_FIELD = (By.ID, "representante_senha")
    
    # Mapeado de 'LOGIN_BTN_ID' da versão anterior.
    LOGIN_BUTTON = (By.ID, "btn_representante")

    # Localizador para a mensagem de erro específica de login
    LOGIN_ERROR_MESSAGE = (By.XPATH, "//div[@class='error' and contains(text(), 'CPF/CNPJ ou senha inválidos!')]")

    # CHUTE: Localizador para a tela de "carregando". PODE PRECISAR DE AJUSTE.
    LOADING_OVERLAY = (By.CLASS_NAME, "loading-overlay")
    
    # Mapeado de 'CAPTCHA_TEXT_X' da versão anterior.
    CAPTCHA = (By.XPATH, "//span[contains(text(), 'Confirme que é humano')]")
    
    # CHUTE: Este localizador não existia. Adicionado com base em um padrão comum para botões de logout.
    LOGOUT_BUTTON = (By.XPATH, "//a[contains(@href, 'logout')]") 

    # Localizador para o logo na navegação principal, usado para voltar à página inicial
    HOME_LOGO_LINK = (By.XPATH, "//aside[@id='main-nav']//img[@alt='Consórcio Servopa']") 

class ServopaGroupLocators:
    """Localizadores para a página de busca de grupo."""
    # Mapeado de 'GRUPO_ID' da versão anterior.
    GROUP_INPUT = (By.ID, "grupo")
    
    # Novo localizador, baseado na função antiga
    COTA_INPUT = (By.ID, "plano")

    # Novo localizador, baseado na função antiga
    DIGITO_INPUT = (By.ID, "digito")
    
    # Mapeado de 'BTN_BUSCAR_ID' da versão anterior.
    SEARCH_GROUP_BUTTON = (By.ID, "btn_busca_usuario")

class ServopaLanceLocators:
    """Localizadores para a página de oferta de lances."""
    # --- Localizadores da lógica antiga, mais robustos ---
    LANCE_CONTEMPLADO_ERROR = (By.XPATH, "//div[contains(@class, 'message-block') and contains(@class, 'error') and contains(., 'Cota já está contemplada')]")
    LANCE_FIDELIDADE_TAB = (By.XPATH, "//div[@class='tab-switcher']//a[text()='Fidelidade']")
    LANCE_FIXO_TAB = (By.XPATH, "//div[@class='tab-switcher']//a[text()='Fixo']")
    LANCE_LIVRE_TAB = (By.XPATH, "//div[@class='tab-switcher']//a[text()='Livre']")
    LANCE_LIVRE_TAB_DATA = (By.CSS_SELECTOR, ".tab-switcher a[data-lance='L']")
    LANCE_ACTIVE_TAB = (By.CSS_SELECTOR, ".tab-switcher a.active")
    # Alguns ambientes usam L maiúsculo, outros minúsculo
    LANCE_LIVRE_PERCENTUAL_INPUT = (By.ID, "tx_Lanliv")
    LANCE_LIVRE_PERCENTUAL_INPUT_ALT = (By.ID, "tx_lanliv")
    LANCE_LIVRE_DESCONTAR_INPUT = (By.ID, "tx_lanliv_emb")
    PROTOCOLO_ANTERIOR_INPUT = (By.ID, "num_protocolo_ant")
    NOME_CLIENTE_TEXT = (By.XPATH, "//span[text()='Consorciado']/following-sibling::h3[1]")
    EXTRATO_CANCELADO_HEADER = (By.XPATH, "//section[@class='main-view']//h2[contains(normalize-space(.), 'Extrato - Cancelado')]")
    # Cabeçalho de Extrato normal (sem o sufixo "- Cancelado")
    EXTRATO_HEADER_NORMAL = (By.XPATH, "//section[@class='main-view']//h2[normalize-space(.)='Extrato']")
    # Versão rápida/absoluta (fornecida pelo usuário) para leitura direta do título
    EXTRATO_HEADER_ANY = (By.XPATH, "/html/body/main/section/div[1]/h2")

    # --- Localizadores antigos que permanecem úteis ---
    OFERTAR_LANCE_BUTTON = (By.XPATH, "//a[contains(., 'Ofertar Lance')]")
    SIMULAR_BUTTON = (By.ID, "btn_simular")
    # Registrar pode ser um <button> ou um <a>; mantemos múltiplos seletores
    REGISTRAR_BUTTON = (By.XPATH, "//button[contains(normalize-space(.), 'Registrar')]")
    REGISTRAR_LINK = (By.XPATH, "//a[normalize-space(.)='Registrar']")
    # XPath absoluto informado pelo usuário (fallback)
    REGISTRAR_ABSOLUTE = (By.XPATH, "/html/body/main/section/div[2]/div/div/div[2]/form/div[6]/a[1]")

    # --- Modal de bloqueio de assembleia (SweetAlert2 / custom) ---
    MODAL_CONTAINER = (By.CSS_SELECTOR, ".swal2-container, .sweet-alert, .swal2-popup")
    MODAL_TEXT = (By.CSS_SELECTOR, ".swal2-container .swal2-html-container, .swal2-content, .sweet-alert p")
    MODAL_OK_BUTTON = (By.CSS_SELECTOR, ".swal2-confirm, .confirm")
    MODAL_OK_BUTTON_BY_TEXT = (By.XPATH, "//button[normalize-space(.)='OK' or normalize-space(.)='Ok' or normalize-space(.)='ok']")