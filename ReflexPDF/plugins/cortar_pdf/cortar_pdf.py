# -*- coding: utf-8 -*-
"""
Created on Sat Nov 29 14:03:32 2025

@author: pjuli
"""

"""
Plugin para cortar um PDF em múltiplos arquivos de tamanho fixo (n páginas cada).
"""

PLUGIN_NAME = "Cortar PDF"
PLUGIN_CATEGORY = "Manipulação"
PLUGIN_DESCRIPTION = "Divide um PDF em vários arquivos menores com número fixo de páginas."
PLUGIN_ICON = None

from PyPDF2 import PdfReader, PdfWriter

def main(input_file: str, output_dir: str, chunk_size: int = 5):
    """
    Divide o PDF em arquivos menores.
    :param input_file: caminho do PDF de entrada
    :param output_dir: diretório de saída
    :param chunk_size: número de páginas por arquivo (default = 5)
    """
    reader = PdfReader(input_file)
    total_pages = len(reader.pages)

    for start in range(0, total_pages, chunk_size):
        writer = PdfWriter()
        end = min(start + chunk_size, total_pages)
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        out_path = f"{output_dir}/parte_{start//chunk_size + 1}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)

        print(f"Gerado: {out_path}")
