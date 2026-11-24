import os
import time
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from pdf2image import convert_from_path, pdfinfo_from_path
from google import genai

# ================= CONFIGURAÇÕES =================
CHAVE_API = ""

ARQUIVO_SAIDA = "extracao_api_gemini.csv"
MODELO = 'gemini-3.6-flash'

# Quantas páginas enviar juntas por requisição (7 páginas x 14 lotes = 98 páginas)
TAMANHO_LOTE = 7

# Mude para 20 se quiser aproveitar as 19 páginas que já foram salvas no CSV
PAGINA_INICIAL = 1

PROMPT = """
Transcreva os dados manuscritos de TODAS as imagens enviadas, na ordem das páginas.
Retorne APENAS o resultado no formato CSV com as colunas separadas por ponto e vírgula (;):
Data;Código;Descrição;Nome
Regras:
- Não adicione nenhum texto, explicação ou resumo antes ou depois do CSV.
- Não use blocos de código markdown (como ```csv).
- Não repita o cabeçalho entre as páginas.
"""
# =================================================

client = genai.Client(api_key=CHAVE_API)

def extrair_lote_gemini(caminhos_imagens, pagina_inicio):
    imagens = []
    try:
        for caminho in caminhos_imagens:
            imagens.append(Image.open(caminho))

        # Tenta até 2 vezes caso atinja o limite de requisições por minuto
        for tentativa in range(2):
            try:
                resposta = client.models.generate_content(
                    model=MODELO,
                    contents=imagens + [PROMPT]
                )
                return resposta.text, False
            except Exception as e:
                erro_str = str(e)
                if "429" in erro_str:
                    if "PerDay" in erro_str or "per day" in erro_str.lower():
                        print(f"\n  [!] Limite diário gratuito atingido na página {pagina_inicio}.")
                        print(f"  [!] Amanhã, altere PAGINA_INICIAL = {pagina_inicio} no código para continuar.")
                        return "", True
                    elif tentativa == 0:
                        print("  Limite por minuto atingido. Aguardando 65 segundos para continuar...")
                        time.sleep(65)
                    else:
                        print(f"  Erro após nova tentativa: {e}")
                        return "", False
                else:
                    print(f"  Erro ao comunicar com a API: {e}")
                    return "", False
        return "", False
    finally:
        for img in imagens:
            img.close()

def selecionar_e_processar():
    root = tk.Tk()
    root.withdraw()

    pdf_path = filedialog.askopenfilename(
        title="Selecione o arquivo PDF manuscrito",
        filetypes=[("Arquivos PDF", "*.pdf")]
    )

    if not pdf_path:
        print("Nenhum arquivo selecionado.")
        return

    nome_arquivo = os.path.basename(pdf_path)
    info = pdfinfo_from_path(pdf_path)
    total_paginas = info["Pages"]

    print(f"\nArquivo selecionado: {nome_arquivo} ({total_paginas} páginas)")
    print(f"Iniciando a partir da página {PAGINA_INICIAL} em lotes de {TAMANHO_LOTE} páginas...\n")

    cabecalho_existe = os.path.exists(ARQUIVO_SAIDA) and os.path.getsize(ARQUIVO_SAIDA) > 0
    with open(ARQUIVO_SAIDA, 'a', encoding='utf-8-sig') as f:
        if not cabecalho_existe:
            f.write("Data;Código;Descrição;Nome\n")

    for inicio in range(PAGINA_INICIAL, total_paginas + 1, TAMANHO_LOTE):
        fim = min(inicio + TAMANHO_LOTE - 1, total_paginas)
        print(f"► Processando páginas {inicio} até {fim} de {total_paginas}...")

        caminhos_temp = convert_from_path(
            pdf_path,
            dpi=200,
            output_folder='/tmp',
            fmt='jpeg',
            paths_only=True,
            first_page=inicio,
            last_page=fim
        )

        dados_csv, limite_diario = extrair_lote_gemini(caminhos_temp, inicio)

        # Limpa as imagens temporárias do disco imediatamente
        for caminho in caminhos_temp:
            if os.path.exists(caminho):
                os.remove(caminho)

        if limite_diario:
            break

        if dados_csv:
            linhas = dados_csv.strip().split('\n')
            with open(ARQUIVO_SAIDA, 'a', encoding='utf-8-sig') as f:
                for linha in linhas:
                    linha = linha.strip()
                    if not linha or linha.startswith("```") or linha.lower().startswith("data;"):
                        continue
                    f.write(f"{linha}\n")

        # Pausa entre lotes para manter o ritmo dentro do plano gratuito
        if fim < total_paginas:
            time.sleep(10)

    print(f"\nProcesso finalizado! Verifique os dados em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    selecionar_e_processar()