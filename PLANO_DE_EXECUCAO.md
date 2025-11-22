# Documentação Técnica do Projeto: Painel de Automação Servopa

# Documentação Técnica do Projeto: Painel de Automação Servopa

## Contexto Atual do Projeto

Este documento detalha o projeto "Painel de Automação Servopa", uma aplicação de desktop com interface gráfica (GUI) desenvolvida em **Tkinter** para automatizar o processo de lances no portal do Consórcio Servopa. 

**Funcionalidades e Fluxos Principais:**

1.  **Automação de Lances (`automacao_servopa.py`):** Utiliza **Selenium WebDriver** para interagir com o navegador. O fluxo inclui login, processamento de cotas e registro de lances.
    *   **Pré-Verificação Inteligente:** Antes de iniciar o navegador, o script realiza uma pré-verificação das cotas fornecidas. Ele compara os números de `grupo`, `cota` e `dígito` de cada entrada com os nomes de arquivos PDF já existentes na pasta do consultor (`Lances/{consultor}`). Esta comparação é feita de forma robusta pela função `_cota_matches_filename` (em `pdf_parser.py`), que extrai e compara conjuntos de dígitos, ignorando formatação e nomes de clientes. Cotas já existentes são puladas, e um relatório detalhado é gerado no log.
    *   **Watchdog Robusto:** A lógica de automação (`automacao_servopa.main`) incorpora um "watchdog" que diferencia `Erros Críticos` (que podem reiniciar o navegador) de `Erros Benignos` (status esperados que não interrompem o fluxo), aumentando a resiliência.
    *   **Organização de PDFs:** Após o download dos comprovantes para `downloads_temporarios`, a função `verificar_e_corrigir_nomes_pdf` (em `pdf_parser.py`) é acionada para organizar esses arquivos.

2.  **Verificação e Organização de Arquivos (`pdf_parser.py`):** A função `verificar_e_corrigir_nomes_pdf` é o coração da gestão de PDFs.
    *   **Lógica de Duas Passadas:** Implementa uma lógica de "quarentena e reavaliação" em duas passadas. Na primeira, renomeia arquivos e move conflitos para uma pasta `Conflitos`. Na segunda, reavalia os arquivos em `Conflitos` para resolver pendências, movendo-os para o destino final se o conflito original for resolvido. A pasta `Conflitos` é automaticamente removida se ficar vazia.
    *   **Versatilidade:** Esta função é usada tanto no final da automação principal (movendo de `downloads_temporarios` para `Lances/{consultor}`) quanto pelo botão "Verificar Nomes na Pasta" (operando "in-place" diretamente em `Lances/{consultor}`).

**Aspectos Técnicos da GUI (`run_automacao.py`):**

*   **Responsividade:** Utiliza `threading` para executar operações demoradas em segundo plano, mantendo a interface responsiva.
*   **Logs em Tempo Real:** A classe `TextRedirector` redireciona `sys.stdout` e `sys.stderr` para um widget de texto na GUI, exibindo logs detalhados em tempo real.
*   **Relatórios Detalhados:** Ao final de cada operação, um relatório formatado com ícones e frases dinâmicas é impresso diretamente no log da interface, substituindo pop-ups.
*   **Editor de Logs:** A interface inclui um editor de logs integrado, permitindo visualizar e salvar alterações em arquivos de log diretamente da aplicação.

**Situação Atual:** O projeto encontra-se em fase de validação final. Todas as funcionalidades principais foram implementadas, bugs conhecidos foram corrigidos, e a documentação técnica está atualizada para refletir a complexidade e robustez do sistema.

## 1. Visão Geral e Objetivo

O objetivo deste projeto é fornecer uma aplicação de desktop robusta para automatizar o processo de lances no portal do Consórcio Servopa, gerenciando login, busca de cotas, oferta de lances e a organização dos comprovantes em PDF através de uma interface gráfica intuitiva.

---

## 2. Arquitetura e Detalhes Técnicos

O sistema é composto por módulos distintos, cada um com uma responsabilidade e tecnologia clara:

- **`run_automacao.py` (Frontend):** O ponto de entrada da aplicação. Constrói e gerencia a GUI **(usando `Tkinter` e o tema `sv-ttk`)**. Gerencia as interações do usuário e executa as operações de backend no módulo **`threading`** para manter a interface responsiva.

- **`automacao_servopa.py` (Backend Orchestrator):** O "motor" da automação. Contém a lógica principal que orquestra o processo de interação com o navegador **(usando `Selenium WebDriver`)**.

- **`pdf_parser.py` (Módulo de Inteligência de Arquivos):** Um módulo especializado responsável por toda a lógica de arquivos PDF, incluindo a extração de dados **(com `pypdf` e `regex`)** e a rotina de verificação e organização de arquivos **(com `os` e `shutil`)**.

- **`locators.py` (Dicionário de Elementos):** Centraliza todos os seletores da página web (XPaths, IDs, etc.) em classes, para serem usados pelo Selenium.

- **`.env` (Configurações):** Arquivo de texto para configurações sensíveis ou que mudam com frequência, carregado no início da aplicação pela biblioteca **`python-dotenv`**.

---

## 3. Fluxos de Trabalho Detalhados

O sistema opera com dois fluxos principais, cada um com sua própria lógica detalhada.

### 3.1. Fluxo Principal: "Iniciar Automação de Lances"

Este é o fluxo para registrar novos lances. Ele é composto por várias etapas inteligentes para garantir eficiência e precisão.

**Etapa 1: Extração e Validação de Cotas (GUI)**
- **Semântica:** O usuário cola o texto com as cotas na interface.
- **Técnica:** A função `parse_lances_from_string` em `automacao_servopa.py` é acionada. Para cada linha de texto, ela:
    1.  Normaliza a linha, substituindo separadores comuns (`,` e `-`) por espaços.
    2.  Divide a string em partes e valida se ela contém exatamente 3 componentes numéricos.
    3.  Linhas mal formatadas são ignoradas e logadas, garantindo que apenas dados válidos prossigam.

**Etapa 2: Pré-Verificação de Cotas Existentes (Backend)**
- **Semântica:** Antes de abrir o navegador, o script verifica se alguma das cotas solicitadas já foi processada e salva na pasta do consultor para evitar trabalho duplicado. Esta etapa é crucial para a eficiência e integridade dos dados.
- **Técnica:**
    1.  O script gera um relatório de log claro na interface, começando com: `--- 🔎 INICIANDO PRÉ-VERIFICAÇÃO... 🔎 ---`.
    2.  Para cada cota fornecida, a função `_cota_matches_filename` (em `pdf_parser.py`) é utilizada. Esta função extrai todos os dígitos da cota (ex: `{'1553', '1', '342', '8'}`) e os compara com os dígitos extraídos de cada nome de arquivo PDF já existente na pasta de destino do consultor.
    3.  A comparação é feita verificando se o conjunto de dígitos da cota é um subconjunto do conjunto de dígitos do nome do arquivo. Esta abordagem numérica ignora nomes de clientes e separadores, oferecendo alta precisão e robustez contra variações de formatação.
    4.  O resultado de cada verificação é logado em tempo real (ex: `[PULANDO] Cota...` se já existir, ou `[OK] Cota...` se for nova).
    5.  Ao final, um resumo é impresso (`- Cotas Recebidas: X, - Cotas Já Existentes: Y, - Novas Cotas a Processar: Z`).
    6.  Se a pasta do consultor não existir, todas as cotas são consideradas novas, e a verificação é pulada para essa pasta específica.

**Etapa 3: Automação com Navegador (Backend)**
- **Semântica:** O robô processa apenas as "Novas Cotas a Processar", ou seja, aquelas que passaram pela pré-verificação.
- **Técnica:** A lógica do `Watchdog Inteligente` entra em ação aqui. A automação diferencia `Erros Críticos` (que reiniciam o navegador) de `Erros Benignos` (status esperados que não interrompem o processo), garantindo robustez e resiliência contra falhas temporárias.

**Etapa 4: Organização Final dos PDFs (Backend)**
- **Semântica:** Ao final da automação, os PDFs recém-baixados na pasta `downloads_temporarios` são organizados e movidos para o destino final.
- **Técnica:** A função `verificar_e_corrigir_nomes_pdf` é chamada, usando `downloads_temporarios` como origem e `Lances/{consultor}` como destino. Ela usa a lógica de duas passadas para renomear e mover os arquivos, gerenciando conflitos de nomes de forma inteligente.

### 3.2. Fluxo Secundário: "Verificar Nomes na Pasta"

- **Semântica:** Esta é uma ferramenta de auditoria para corrigir nomes em uma pasta de consultor já povoada, sem envolver downloads temporários.
- **Técnica:** O botão aciona a mesma função `verificar_e_corrigir_nomes_pdf`, mas passando a pasta do consultor (ex: `Lances/Raphael`) como **origem e destino**. Isso aciona a lógica de correção "no mesmo lugar", renomeando arquivos incorretos e gerenciando conflitos sem a necessidade da pasta de downloads.

---

## 4. Detalhes Técnicos da Interface (GUI)

- **Responsividade com Threads:** A GUI (`run_automacao.py`) utiliza o módulo `threading` para executar todas as operações demoradas (automação e verificação) em uma thread separada. Isso impede que a janela principal congele. O método `root.after()` é usado para verificar o status da thread em intervalos de 100ms sem bloquear o loop principal da interface.
- **Redirecionamento de Log em Tempo Real:** A classe `TextRedirector` é usada para interceptar a saída padrão (`sys.stdout`). Qualquer comando `print()` ou log de bibliotecas é redirecionado em tempo real para o widget de texto na GUI, fornecendo feedback visual instantâneo ao usuário.
- **Gerenciamento de Estado da UI:** Funções como `set_ui_state()` são usadas para desabilitar e habilitar botões e campos de entrada de forma centralizada. Isso previne que o usuário inicie múltiplas operações simultaneamente, garantindo que apenas uma `active_thread` esteja em execução por vez.

---

## 5. Histórico de Correções e Melhorias

Durante o desenvolvimento, foram realizadas correções críticas, incluindo a refatoração do `locators.py`, recriação de funções ausentes no `pdf_parser.py`, correção de inconsistências de comunicação entre a GUI e o backend, e a implementação de um sistema de relatório final no log. A lógica foi refinada para suportar os múltiplos fluxos de trabalho descritos acima.

---

## 6. Próximo Passo: Teste e Validação Final

Com todas as correções e aprimoramentos implementados, o próximo passo é realizar um teste completo e validar o funcionamento de todas as funcionalidades em um ambiente real. Após a validação, o projeto estará pronto para a geração do executável (.exe).
