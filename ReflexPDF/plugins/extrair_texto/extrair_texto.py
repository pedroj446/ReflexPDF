# -*- coding: utf-8 -*-
"""
Created on Sat Nov 29 13:47:53 2025

@author: pjuli
"""

"""
Extrai texto de um PDF e salva em arquivo .txt
"""

from PyPDF2 import PdfReader

def main(input_file: str, output_dir: str):
    reader = PdfReader(input_file)
    texto = ""
    for page in reader.pages:
        texto += page.extract_text() + "\n"

    out_path = f"{output_dir}/saida.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(texto)

    print(f"Texto extraído para {out_path}")
