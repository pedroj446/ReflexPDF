# -*- coding: utf-8 -*-
"""
Created on Sat Nov 29 13:48:11 2025

@author: pjuli
"""

"""
Plugin para juntar múltiplos PDFs em um único arquivo.
"""

PLUGIN_NAME = "Juntar PDFs"
PLUGIN_CATEGORY = "Manipulação"
PLUGIN_DESCRIPTION = "Une vários arquivos PDF em um único documento."
PLUGIN_ICON = None  # opcional: caminho para ícone

from PyPDF2 import PdfMerger

def main(input_file1: str, input_file2: str, output_dir: str):
    """
    Junta dois PDFs em um único arquivo.
    Pode ser expandido para aceitar mais arquivos.
    """
    merger = PdfMerger()
    merger.append(input_file1)
    merger.append(input_file2)

    out_path = f"{output_dir}/juntado.pdf"
    merger.write(out_path)
    merger.close()

    print(f"PDFs unidos em {out_path}")
