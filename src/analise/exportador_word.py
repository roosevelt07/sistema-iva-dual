"""Exportação do relatório de análise em Word (.docx)."""

import io
import os
from decimal import Decimal

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    DOCX_DISPONIVEL = True
except ImportError:
    DOCX_DISPONIVEL = False

from src.analise.decisao import ResultadoAnalise
from src.analise.formatters import fmt_moeda
from src.analise.narrativa import gerar_narrativa

_VERDE = RGBColor(0x2E, 0x8B, 0x57) if DOCX_DISPONIVEL else None


def _detalhes_monetarios(detalhes: dict) -> dict:
    return {k: v for k, v in detalhes.items() if isinstance(v, Decimal)}


def _titulo_verde(doc, texto, level):
    heading = doc.add_heading(texto, level=level)
    heading.runs[0].font.color.rgb = _VERDE
    return heading


def _adicionar_borda_paragrafo(paragrafo) -> None:
    """Borda verde ao redor do parágrafo (recomendação em destaque)."""
    p_pr = paragrafo._p.get_or_add_pPr()
    borda = OxmlElement("w:pBdr")
    for lado in ("top", "left", "bottom", "right"):
        elemento = OxmlElement(f"w:{lado}")
        elemento.set(qn("w:val"), "single")
        elemento.set(qn("w:sz"), "12")
        elemento.set(qn("w:color"), "2E8B57")
        elemento.set(qn("w:space"), "4")
        borda.append(elemento)
    p_pr.append(borda)


def gerar_word(resultado: ResultadoAnalise, nome_cliente: str, data_relatorio, observacoes: str = "") -> bytes:
    """Gera o relatório Word e retorna os bytes do arquivo .docx."""
    if not DOCX_DISPONIVEL:
        raise RuntimeError("python-docx não está instalado.")

    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b

    doc = Document()

    # 1. Capa
    if os.path.exists("logo.png"):
        doc.add_picture("logo.png", width=Inches(1.5))
    titulo = doc.add_heading("Análise IVA Dual — LC 214/2025", level=0)
    titulo.runs[0].font.color.rgb = _VERDE
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph(f"Cliente: {nome_cliente or '—'}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph(f"Data: {data_relatorio}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 2. Resumo executivo
    _titulo_verde(doc, "Resumo executivo", level=1)
    doc.add_paragraph(gerar_narrativa(resultado))

    # 3. Comparativo de carga
    _titulo_verde(doc, "Comparativo de carga tributária", level=1)
    tabela = doc.add_table(rows=1, cols=4)
    tabela.style = "Light Grid Accent 1"
    for i, texto in enumerate(["Item", "Carga Atual (R$)", "Carga IVA (R$)", "Diferença (R$)"]):
        tabela.rows[0].cells[i].text = texto
    linhas = [
        ("Carga bruta", cenario_a.carga_bruta, cenario_b.carga_bruta),
        ("Crédito aproveitado", cenario_a.credito_aproveitado, cenario_b.credito_aproveitado),
        ("Carga líquida", cenario_a.carga_liquida, cenario_b.carga_liquida),
    ]
    for nome, valor_a, valor_b in linhas:
        linha = tabela.add_row().cells
        linha[0].text = nome
        linha[1].text = fmt_moeda(valor_a)
        linha[2].text = fmt_moeda(valor_b)
        linha[3].text = fmt_moeda(valor_a - valor_b)

    # 4. Recomendação
    _titulo_verde(doc, "Recomendação", level=1)
    p = doc.add_paragraph()
    run = p.add_run(
        "Migrar para o regime regular do IBS/CBS."
        if resultado.recomendacao == "MIGRAR_REGIME_REGULAR"
        else "Manter o regime atual."
    )
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = _VERDE
    _adicionar_borda_paragrafo(p)

    # 5. Memória de cálculo
    _titulo_verde(doc, "Memória de cálculo", level=1)
    for cenario in (cenario_a, cenario_b):
        doc.add_heading(cenario.nome, level=2)
        detalhes = _detalhes_monetarios(cenario.detalhes)
        tabela_mem = doc.add_table(rows=1, cols=2)
        tabela_mem.style = "Light List Accent 1"
        tabela_mem.rows[0].cells[0].text = "Item"
        tabela_mem.rows[0].cells[1].text = "Valor"
        for chave, valor in detalhes.items():
            linha = tabela_mem.add_row().cells
            linha[0].text = chave
            linha[1].text = fmt_moeda(valor)

    # 6. Alertas e ressalvas
    if resultado.alertas:
        _titulo_verde(doc, "Alertas e ressalvas", level=1)
        for alerta in resultado.alertas:
            doc.add_paragraph(alerta, style="List Bullet")

    if observacoes:
        _titulo_verde(doc, "Observações adicionais", level=1)
        doc.add_paragraph(observacoes)

    # 7. Rodapé
    rodape = doc.sections[0].footer.paragraphs[0]
    rodape.text = "Simulação baseada na LC 214/2025 — valores estimados."
    rodape.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
