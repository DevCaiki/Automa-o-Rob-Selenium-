import re
import os
import shutil
import logging
from pypdf import PdfReader

# Configuração básica de logging para este módulo
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def extract_canonical_cota(text):
    """
    Extrai um conjunto canônico (grupo, cota, digito) de uma string de texto.
    """
    if not text:
        return "Não encontrado"
    
    parts = re.findall(r'\d+', str(text))
    
    if not parts:
        return None

    if len(parts) == 1:
        full_number = parts[0]
        if len(full_number) > 5:
             digito = full_number[-1]
             grupo = full_number[:4]
             cota = full_number[4:-1]
             return (grupo, cota, digito)
        else:
            return None

    digito = parts.pop(-1)
    remaining_string = "".join(parts)

    if len(remaining_string) < 4:
        return None

    grupo = remaining_string[:4]
    cota = remaining_string[4:]
    
    return (grupo, cota, digito)

def parse_cota_from_filename(filename):
    """Extrai (grupo, cota, digito) de um nome de arquivo formatado."""
    match = re.search(r'LANCE[- ]?(\d{4})[.,\s]?([\d,]+)[-\s]?(\d)\.pdf', filename, re.IGNORECASE)
    if match:
        grupo = match.group(1)
        cota = match.group(2)
        digito = match.group(3)
        return (grupo, cota, digito)
    return None

def _extrair_info_pdf(caminho_pdf):
    """Função interna para extrair nome, grupo, cota e digito de um PDF, com logging objetivo."""
    try:
        filename_only = os.path.basename(caminho_pdf)
        logging.info(f"---- Analisando PDF: {filename_only} ----")
        
        reader = PdfReader(caminho_pdf)
        if not reader.pages:
            logging.warning(f"PDF '{filename_only}' corrompido ou sem páginas.")
            return None, None, None, None, "PDF corrompido ou sem páginas"
        
        texto = "".join(page.extract_text() or "" for page in reader.pages)
        texto_limpo = re.sub(r'\s+', ' ', texto).strip()

        nome_match = re.search(r"Consorciado\s*[:\-]?\s*([A-ZÀ-Ú\s]{5,})", texto_limpo, re.IGNORECASE)
        nome = nome_match.group(1).strip().upper() if nome_match else None

        grupo_extracted = None
        cota_extracted = None
        digito_extracted = None

        # Regex para o padrão da cota: 4 dígitos (grupo) [separador] [dígitos/vírgulas] (cota) - [1 dígito] (dígito)
        cota_pattern_in_text = r"(\d{4})[.,\s]?([\d,]+)[-\s]?(\d)"
        
        # Priorizar busca da cota após o nome do consorciado
        if nome:
            escaped_nome = re.escape(nome)
            match = re.search(rf"{escaped_nome}\s*{cota_pattern_in_text}", texto_limpo, re.IGNORECASE)
            if match:
                grupo_extracted = match.group(1)
                cota_extracted = match.group(2)
                digito_extracted = match.group(3)
        
        # Se não encontrou após o nome, tentar após o label "Cota"
        if not grupo_extracted:
            match = re.search(rf"Cota\s*{cota_pattern_in_text}", texto_limpo, re.IGNORECASE)
            if match:
                grupo_extracted = match.group(1)
                cota_extracted = match.group(2)
                digito_extracted = match.group(3)

        # Se ainda não encontrou, tentar uma busca geral pelo padrão da cota no texto
        if not grupo_extracted:
            match = re.search(cota_pattern_in_text, texto_limpo)
            if match:
                grupo_extracted = match.group(1)
                cota_extracted = match.group(2)
                digito_extracted = match.group(3)


        if nome and grupo_extracted and cota_extracted and digito_extracted:
            logging.info(f"  -> Sucesso: Nome '{nome}', Grupo '{grupo_extracted}', Cota '{cota_extracted}', Dígito '{digito_extracted}' encontrados.")
            return nome, grupo_extracted, cota_extracted, digito_extracted, None
        else:
            erro_msg = f"  -> Falha: Nome ({'ENCONTRADO' if nome else 'NÃO ENCONTRADO'}) ou Cota (Grupo/Cota/Dígito {'ENCONTRADOS' if grupo_extracted else 'NÃO ENCONTRADOS'}) no PDF."
            logging.warning(erro_msg)
            return None, None, None, None, erro_msg

    except Exception as e:
        logging.error(f"Erro crítico ao ler PDF '{os.path.basename(caminho_pdf)}': {e}", exc_info=True)
        return None, None, None, None, f"Erro crítico de leitura do PDF: {e}"

def parse_cota_from_filename(filename):
    """Extrai (grupo, cota, digito) de um nome de arquivo formatado."""
    match = re.search(r'LANCE[- ]?(\d{4})[.,\s]?([\d,]+)[-\s]?(\d)\.pdf', filename, re.IGNORECASE)
    if match:
        grupo = match.group(1)
        cota = match.group(2)
        digito = match.group(3)
        return (grupo, cota, digito)
    return None
        

def verificar_e_corrigir_nomes_pdf(consultor_path):
    """Verifica e corrige os nomes dos arquivos PDF em uma pasta, usando uma estratégia de quarentena para conflitos."""
    logging.info(f"--- Iniciando verificação de nomes em: {consultor_path} ---")
    report = {
        'total_scanned': 0, 'renamed': 0, 'correct': 0, 
        'conflicts': 0, 'errors': 0
    }
    conflitos_path = os.path.join(consultor_path, "Conflitos")
    arquivos_para_renomear = []

    # 1ª Passada: Identificar arquivos a serem renomeados
    pdf_files = [f for f in os.listdir(consultor_path) if f.lower().endswith('.pdf') and f.upper().startswith("LANCE")]
    report['total_scanned'] = len(pdf_files)

    for filename in pdf_files:
        caminho_completo = os.path.join(consultor_path, filename)
        nome_pdf, grupo_pdf, cota_pdf, digito_pdf, erro = _extrair_info_pdf(caminho_completo)

        if erro:
            logging.warning(f"Erro ao ler '{filename}': {erro}")
            report['errors'] += 1
            continue

        nome_sanitizado = re.sub(r'[\/:*?"<>|]', '_', nome_pdf)
        novo_nome = f"LANCE- {nome_sanitizado} {grupo_pdf}.{cota_pdf}-{digito_pdf}.pdf"

        if filename == novo_nome:
            report['correct'] += 1
        else:
            arquivos_para_renomear.append((caminho_completo, novo_nome))

    if not arquivos_para_renomear:
        logging.info("Nenhum arquivo precisa ser renomeado.")
        return report

    # --- DEBUG LOGS --- (Adicionado para depuração)
    logging.info("--- DEBUG: Detalhes dos arquivos para renomear ---")
    for caminho_antigo, novo_nome_debug in arquivos_para_renomear:
        filename_debug = os.path.basename(caminho_antigo)
        logging.info(f"DEBUG: Original: '{filename_debug}' (bytes={filename_debug.encode('utf-8')})")
        logging.info(f"DEBUG: Novo Nome: '{novo_nome_debug}' (bytes={novo_nome_debug.encode('utf-8')})")
        logging.info(f"DEBUG: Comparação: {filename_debug == novo_nome_debug}")
    logging.info("--- FIM DEBUG ---")

    # 2ª Passada: Renomear com tratamento de conflitos
    for caminho_antigo, novo_nome in arquivos_para_renomear:
        caminho_novo = os.path.join(consultor_path, novo_nome)
        try:
            if os.path.exists(caminho_novo):
                logging.warning(f"CONFLITO: O destino '{novo_nome}' já existe. Movendo original para a pasta de quarentena.")
                if not os.path.exists(conflitos_path):
                    os.makedirs(conflitos_path)
                shutil.move(caminho_antigo, os.path.join(conflitos_path, os.path.basename(caminho_antigo)))
                report['conflicts'] += 1
            else:
                os.rename(caminho_antigo, caminho_novo)
                logging.info(f"CORRIGIDO: '{os.path.basename(caminho_antigo)}' -> '{novo_nome}'")
                report['renamed'] += 1
        except Exception as e:
            logging.error(f"FALHA AO RENOMEAR '{os.path.basename(caminho_antigo)}': {e}")
            report['errors'] += 1

    # 3ª Passada: Tentar resolver quarentena
    if os.path.exists(conflitos_path):
        logging.info("--- Tentando resolver arquivos em quarentena ---")
        for filename in os.listdir(conflitos_path):
            caminho_quarentena = os.path.join(conflitos_path, filename)
            nome_pdf, cota_pdf, _ = _extrair_info_pdf(caminho_quarentena)
            if nome_pdf and cota_pdf:
                nome_sanitizado = re.sub(r'[\/:*?"<>|]', '_', nome_pdf)
                novo_nome_final = f"LANCE- {nome_sanitizado} {cota_pdf}.pdf"
                caminho_final = os.path.join(consultor_path, novo_nome_final)
                if not os.path.exists(caminho_final):
                    shutil.move(caminho_quarentena, caminho_final)
                    logging.info(f"RESOLVIDO: '{filename}' movido para '{novo_nome_final}'")
                    report['conflicts'] -= 1 # Conflito resolvido
                    report['renamed'] += 1
                else:
                    logging.error(f"NÃO RESOLVIDO: Conflito para '{filename}' persiste. O arquivo permanece em quarentena.")
        
        if not os.listdir(conflitos_path):
            os.rmdir(conflitos_path)
            logging.info("Pasta de conflitos resolvida e removida.")

    logging.info("--- Verificação de nomes finalizada ---")
    return report


