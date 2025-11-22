import sys
from pypdf import PdfReader
import re

def extract_text_from_pdf(pdf_path):
    """Lê um arquivo PDF e imprime o texto extraído de todas as páginas."""
    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            print(f"ERRO: O arquivo PDF '{pdf_path}' está corrompido ou não contém páginas.")
            return

        print(f"--- Lendo texto do arquivo: {pdf_path} ---\
")
        texto_completo = ""
        for i, page in enumerate(reader.pages):
            raw_text = page.extract_text() or ""
            print(f"--- TEXTO BRUTO (PÁGINA {i+1}) ---")
            print(raw_text)
            print("-------------------------------------\
")
            texto_completo += raw_text + "\n"
        
        # Mostra o texto "limpo" que o robô usa para procurar os padrões
        texto_limpo = re.sub(r'\s+', ' ', texto_completo).strip()
        print("--- TEXTO CONSOLIDADO E LIMPO (como o robô vê) ---")
        print(texto_limpo)
        print("-----------------------------------------------------")

    except FileNotFoundError:
        print(f"ERRO: Arquivo não encontrado em '{pdf_path}'")
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao ler o PDF: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python debug_pdf_text.py \"caminho/completo/para/o/arquivo.pdf\"")
        print("Exemplo: python debug_pdf_text.py \"Lances/Ingryd/LANCE- JOAO HAROLDO AJALA FERNANDES 1553.2387-3.pdf\"")
    else:
        pdf_file_path = sys.argv[1]
        extract_text_from_pdf(pdf_file_path)
