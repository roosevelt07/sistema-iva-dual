"""Exportação do relatório de análise em PowerPoint (.pptx)."""

import io
import os
from decimal import Decimal

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Cm, Pt

    PPTX_DISPONIVEL = True
except ImportError:
    PPTX_DISPONIVEL = False

from src.analise.decisao import ResultadoAnalise
from src.analise.formatters import fmt_moeda, fmt_percentual
from src.analise.graficos import grafico_barra_comparativo

_VERDE = RGBColor(0x2E, 0x8B, 0x57) if PPTX_DISPONIVEL else None
_PRETO = RGBColor(0x1A, 0x1A, 0x1A) if PPTX_DISPONIVEL else None
_BRANCO = RGBColor(0xFF, 0xFF, 0xFF) if PPTX_DISPONIVEL else None
_CINZA_CLARO = RGBColor(0xF0, 0xF0, 0xF0) if PPTX_DISPONIVEL else None
_VERMELHO = RGBColor(0xC0, 0x39, 0x2B) if PPTX_DISPONIVEL else None


def _fundo(slide, cor):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = cor


def _caixa_texto(slide, texto, left, top, width, height, tamanho=18, cor=None,
                  negrito=False, alinhamento=PP_ALIGN.LEFT, fonte="Calibri"):
    caixa = slide.shapes.add_textbox(left, top, width, height)
    tf = caixa.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = alinhamento
    run = p.add_run()
    run.text = texto
    run.font.size = Pt(tamanho)
    run.font.name = fonte
    run.font.bold = negrito
    if cor is not None:
        run.font.color.rgb = cor
    return caixa


def gerar_ppt(resultado: ResultadoAnalise, nome_cliente: str, data_relatorio) -> bytes:
    """Gera a apresentação PPT e retorna os bytes do arquivo .pptx."""
    if not PPTX_DISPONIVEL:
        raise RuntimeError("python-pptx não está instalado.")

    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b

    prs = Presentation()
    prs.slide_width = Cm(33.87)
    prs.slide_height = Cm(19.05)
    layout_branco = prs.slide_layouts[6]

    # 1. Slide capa
    slide = prs.slides.add_slide(layout_branco)
    _fundo(slide, _PRETO)
    _caixa_texto(
        slide, "Análise IVA Dual", Cm(2), Cm(6), Cm(24), Cm(3),
        tamanho=40, cor=_VERDE, negrito=True,
    )
    _caixa_texto(
        slide, f"{nome_cliente or '—'} — {data_relatorio}", Cm(2), Cm(10), Cm(24), Cm(2),
        tamanho=20, cor=_BRANCO,
    )
    if os.path.exists("logo.png"):
        slide.shapes.add_picture("logo.png", Cm(28), Cm(1), height=Cm(3))

    # 2. Slide resumo executivo — 3 métricas
    slide = prs.slides.add_slide(layout_branco)
    _fundo(slide, _BRANCO)
    _caixa_texto(slide, "Resumo executivo", Cm(1.5), Cm(1), Cm(20), Cm(1.5), tamanho=28, cor=_PRETO, negrito=True)
    metricas = [
        ("Carga Atual", fmt_moeda(cenario_a.carga_liquida)),
        ("Carga IVA", fmt_moeda(cenario_b.carga_liquida)),
        ("Economia", fmt_moeda(abs(resultado.delta_absoluto))),
    ]
    for i, (label, valor) in enumerate(metricas):
        esquerda = Cm(1.5 + i * 10.5)
        _caixa_texto(slide, valor, esquerda, Cm(4), Cm(9), Cm(2), tamanho=32, cor=_VERDE,
                     negrito=True, alinhamento=PP_ALIGN.CENTER)
        _caixa_texto(slide, label, esquerda, Cm(6), Cm(9), Cm(1.2), tamanho=16, cor=_PRETO,
                     alinhamento=PP_ALIGN.CENTER)

    # 3. Slide comparativo de carga — tabela
    slide = prs.slides.add_slide(layout_branco)
    _fundo(slide, _BRANCO)
    _caixa_texto(slide, "Comparativo de carga tributária", Cm(1.5), Cm(1), Cm(20), Cm(1.5),
                 tamanho=28, cor=_PRETO, negrito=True)
    linhas_dados = [
        ("Carga bruta", cenario_a.carga_bruta, cenario_b.carga_bruta),
        ("Crédito aproveitado", cenario_a.credito_aproveitado, cenario_b.credito_aproveitado),
        ("Carga líquida", cenario_a.carga_liquida, cenario_b.carga_liquida),
    ]
    tabela_shape = slide.shapes.add_table(len(linhas_dados) + 1, 5, Cm(1.5), Cm(3), Cm(30), Cm(8))
    tabela = tabela_shape.table
    for c, texto in enumerate(["Item", "R$ Atual", "% Atual", "R$ IVA", "Economia"]):
        celula = tabela.cell(0, c)
        celula.text = texto
        celula.fill.solid()
        celula.fill.fore_color.rgb = _VERDE
        for run in celula.text_frame.paragraphs[0].runs:
            run.font.color.rgb = _BRANCO
            run.font.bold = True
    for i, (nome, valor_a, valor_b) in enumerate(linhas_dados, start=1):
        faturamento = resultado.ctx.faturamento
        pct_a = (valor_a / faturamento * 100) if faturamento else Decimal("0")
        valores_linha = [
            nome, fmt_moeda(valor_a), fmt_percentual(pct_a),
            fmt_moeda(valor_b), fmt_moeda(valor_a - valor_b),
        ]
        for c, texto in enumerate(valores_linha):
            celula = tabela.cell(i, c)
            celula.text = texto
            celula.fill.solid()
            celula.fill.fore_color.rgb = _CINZA_CLARO if i % 2 == 0 else _BRANCO

    # 4. Slide recomendação
    slide = prs.slides.add_slide(layout_branco)
    migrar = resultado.recomendacao == "MIGRAR_REGIME_REGULAR"
    _fundo(slide, _VERDE if migrar else _PRETO)
    texto_recomendacao = "✓ MIGRAR PARA REGIME REGULAR" if migrar else "→ MANTER REGIME ATUAL"
    _caixa_texto(slide, texto_recomendacao, Cm(2), Cm(7), Cm(30), Cm(3), tamanho=36, cor=_BRANCO,
                 negrito=True, alinhamento=PP_ALIGN.CENTER)
    subtexto = f"Delta: {fmt_moeda(resultado.delta_absoluto)} ({fmt_percentual(resultado.delta_percentual)})"
    _caixa_texto(slide, subtexto, Cm(2), Cm(10.5), Cm(30), Cm(2), tamanho=24, cor=_BRANCO,
                 alinhamento=PP_ALIGN.CENTER)

    # 5. Slide gráfico comparativo
    slide = prs.slides.add_slide(layout_branco)
    _fundo(slide, _BRANCO)
    _caixa_texto(slide, "Gráfico comparativo", Cm(1.5), Cm(1), Cm(20), Cm(1.5),
                 tamanho=28, cor=_PRETO, negrito=True)
    try:
        fig = grafico_barra_comparativo(resultado)
        imagem_bytes = fig.to_image(format="png", width=1200, height=500, engine="kaleido")
        slide.shapes.add_picture(io.BytesIO(imagem_bytes), Cm(2), Cm(3), width=Cm(30))
        _caixa_texto(slide, "Fonte: Simulação LC 214/2025", Cm(2), Cm(17), Cm(20), Cm(1),
                     tamanho=12, cor=_PRETO)
    except Exception:
        _caixa_texto(
            slide, "Gráfico não disponível nesta exportação (kaleido não instalado).",
            Cm(2), Cm(8), Cm(28), Cm(2), tamanho=18, cor=_PRETO,
        )

    # 6. Slide alertas e próximos passos
    slide = prs.slides.add_slide(layout_branco)
    _fundo(slide, _BRANCO)
    _caixa_texto(slide, "Pontos de Atenção", Cm(1.5), Cm(1), Cm(20), Cm(1.5),
                 tamanho=28, cor=_PRETO, negrito=True)
    caixa = slide.shapes.add_textbox(Cm(1.5), Cm(3), Cm(30), Cm(13))
    tf = caixa.text_frame
    tf.word_wrap = True
    primeiro = True

    def _proxima_linha():
        nonlocal primeiro
        if primeiro:
            primeiro = False
            return tf.paragraphs[0]
        return tf.add_paragraph()

    for alerta in resultado.alertas:
        p = _proxima_linha()
        p.text = f"• {alerta}"
        p.font.size = Pt(16)
        p.font.color.rgb = _VERMELHO

    proximos_passos = [
        "Confirmar dados de compras e crédito com o financeiro do cliente.",
        "Revisar enquadramento tributário antes de decidir a migração.",
    ]
    for passo in proximos_passos:
        p = _proxima_linha()
        p.text = f"• {passo}"
        p.font.size = Pt(16)
        p.font.color.rgb = _VERDE

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
