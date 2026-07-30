"""Gráficos Plotly reutilizáveis para o Analisador IVA.

Sem dependência de Streamlit — recebe tipos do motor (ResultadoAnalise,
ContextoCalculo) ou dicts já prontos e devolve `go.Figure`, testável de
forma isolada.
"""

from decimal import Decimal
from typing import Dict

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.analise.config_lc214 import get_aliquotas_ano, get_reducao_icms_iss
from src.analise.decisao import ResultadoAnalise
from src.analise.formatters import fmt_moeda
from src.analise.formulario import ContextoCalculo

CORES = {
    "verde": "#2E8B57",
    "verde_claro": "#52C27A",
    "verde_escuro": "#1A5C38",
    "preto": "#1A1A1A",
    "cinza_escuro": "#444444",
    "cinza_medio": "#888888",
    "cinza_claro": "#CCCCCC",
    "branco": "#FFFFFF",
    "vermelho": "#C0392B",
    "amarelo": "#F1C40F",  # não veio na paleta fornecida — completado para o gauge
}

LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#1A1A1A"),
    margin=dict(l=20, r=20, t=40, b=20),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=-0.3,
        xanchor="center", x=0.5,
    ),
    separators=",.",  # vírgula decimal, ponto de milhar — padrão BR em toda a figura
)

_ROTULOS_CENARIO_A = {
    "ibs_cbs_das": "IBS/CBS (DAS)",
    "pis_cofins": "PIS/COFINS",
    "pis_cofins_bruto": "PIS/COFINS",
    "icms": "ICMS",
    "iss": "ISS",
}


def grafico_pizzas_comparativo(resultado: ResultadoAnalise) -> go.Figure:
    """Dois donuts lado a lado: carga atual vs. carga IVA."""
    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b
    ctx = resultado.ctx

    labels_a, valores_a = [], []
    for chave, valor in cenario_a.detalhes.items():
        if chave in _ROTULOS_CENARIO_A and isinstance(valor, Decimal) and valor > 0:
            labels_a.append(_ROTULOS_CENARIO_A[chave])
            valores_a.append(float(valor))
    cores_a = [CORES["preto"], CORES["cinza_escuro"], CORES["cinza_medio"], CORES["cinza_claro"]]

    cbs_valor = cenario_b.detalhes.get("cbs_novo")
    ibs_valor = cenario_b.detalhes.get("ibs_novo")
    if cbs_valor is None or ibs_valor is None:
        cbs_valor = cenario_b.carga_bruta * (ctx.cbs_efetiva / ctx.ibs_cbs_total)
        ibs_valor = cenario_b.carga_bruta * (ctx.ibs_efetiva / ctx.ibs_cbs_total)

    pares_b = [
        ("CBS", cbs_valor, CORES["verde_escuro"]),
        ("IBS", ibs_valor, CORES["verde"]),
        ("Crédito aproveitado", cenario_b.credito_aproveitado, CORES["verde_claro"]),
    ]
    labels_b, valores_b, cores_b = [], [], []
    for nome, valor, cor in pares_b:
        if valor > 0:
            labels_b.append(nome)
            valores_b.append(float(valor))
            cores_b.append(cor)

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "pie"}, {"type": "pie"}]],
        subplot_titles=("Composição carga atual", "Composição carga IVA Regular"),
    )
    fig.add_trace(
        go.Pie(
            labels=labels_a, values=valores_a, hole=0.35,
            marker=dict(colors=cores_a[: len(labels_a)]),
            textinfo="percent+label",
            customdata=[fmt_moeda(v) for v in valores_a],
            hovertemplate="%{label}<br>%{customdata}<br>%{percent}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Pie(
            labels=labels_b, values=valores_b, hole=0.35,
            marker=dict(colors=cores_b),
            textinfo="percent+label",
            customdata=[fmt_moeda(v) for v in valores_b],
            hovertemplate="%{label}<br>%{customdata}<br>%{percent}<extra></extra>",
        ),
        row=1, col=2,
    )
    fig.update_layout(**LAYOUT_BASE, height=340, showlegend=True)
    return fig


def grafico_barra_comparativo(resultado: ResultadoAnalise) -> go.Figure:
    """Barras horizontais empilhadas: Atual vs. IVA."""
    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b
    ctx = resultado.ctx

    fig = go.Figure()

    for chave, valor in cenario_a.detalhes.items():
        if chave in _ROTULOS_CENARIO_A and isinstance(valor, Decimal) and valor > 0:
            fig.add_trace(
                go.Bar(
                    name=f"Atual — {_ROTULOS_CENARIO_A[chave]}",
                    y=["Atual"], x=[float(valor)], orientation="h",
                    marker=dict(color=CORES["preto"]),
                    text=[fmt_moeda(valor)], textposition="outside",
                )
            )

    cbs_valor = ctx.faturamento * ctx.cbs_efetiva
    ibs_valor = ctx.faturamento * ctx.ibs_efetiva
    credito_valor = cenario_b.credito_aproveitado

    fig.add_trace(
        go.Bar(
            name="IVA — CBS", y=["IVA"], x=[float(cbs_valor)], orientation="h",
            marker=dict(color=CORES["verde_escuro"]),
            text=[fmt_moeda(cbs_valor)], textposition="outside",
        )
    )
    fig.add_trace(
        go.Bar(
            name="IVA — IBS", y=["IVA"], x=[float(ibs_valor)], orientation="h",
            marker=dict(color=CORES["verde"]),
            text=[fmt_moeda(ibs_valor)], textposition="outside",
        )
    )
    if credito_valor > 0:
        fig.add_annotation(
            x=float(cenario_b.carga_bruta),
            y="IVA",
            text=f"Crédito deduzido: {fmt_moeda(credito_valor)}",
            showarrow=True,
            arrowhead=2,
            ax=40, ay=0,
            font=dict(color=CORES["verde_escuro"], size=12),
        )

    menor = min(float(cenario_a.carga_liquida), float(cenario_b.carga_liquida))
    fig.add_vline(x=menor, line_dash="dot", line_color=CORES["cinza_medio"])

    fig.update_layout(
        **LAYOUT_BASE,
        barmode="stack",
        title="Comparativo de carga tributária",
        xaxis_title="R$",
        height=320,
    )
    return fig


def grafico_gauge_aliquota(resultado: ResultadoAnalise) -> go.Figure:
    """Dois gauges: alíquota efetiva atual vs. IVA."""
    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b
    aliquota_atual = float(cenario_a.aliquota_efetiva * 100)
    aliquota_iva = float(cenario_b.aliquota_efetiva * 100)

    steps = [
        {"range": [0, 15], "color": CORES["verde"]},
        {"range": [15, 20], "color": CORES["amarelo"]},
        {"range": [20, 30], "color": CORES["vermelho"]},
    ]
    threshold = dict(line=dict(color=CORES["vermelho"], width=3), thickness=0.85, value=26.5)

    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "indicator"}, {"type": "indicator"}]])
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=aliquota_atual,
            number=dict(suffix="%", valueformat=".2f"),
            title=dict(text="Carga Atual"),
            gauge=dict(
                axis=dict(range=[0, 30]), bar=dict(color=CORES["preto"]),
                steps=steps, threshold=threshold,
            ),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=aliquota_iva,
            number=dict(suffix="%", valueformat=".2f"),
            delta=dict(
                reference=aliquota_atual, valueformat=".2f", suffix="%",
                decreasing=dict(color=CORES["verde"]), increasing=dict(color=CORES["vermelho"]),
            ),
            title=dict(text="Carga IVA Regular"),
            gauge=dict(
                axis=dict(range=[0, 30]), bar=dict(color=CORES["verde"]),
                steps=steps, threshold=threshold,
            ),
        ),
        row=1, col=2,
    )
    fig.update_layout(**LAYOUT_BASE, height=280)
    return fig


def grafico_pizza_atual(carga: Dict[str, Decimal]) -> go.Figure:
    """Donut único com PIS, COFINS, ICMS, ISS, IPI (Modo Sistema Atual)."""
    cores_tributos = {
        "PIS": "#444444",
        "COFINS": "#666666",
        "ICMS": "#1A1A1A",
        "ISS": "#888888",
        "IPI": "#2E8B57",
    }

    labels, valores, cores = [], [], []
    for nome, valor in carga.items():
        if valor and valor > 0:
            labels.append(nome)
            valores.append(float(valor))
            cores.append(cores_tributos.get(nome, CORES["cinza_medio"]))

    fig = go.Figure(
        go.Pie(
            labels=labels, values=valores, hole=0.4,
            marker=dict(colors=cores), textinfo="label+percent",
            customdata=[fmt_moeda(v) for v in valores],
            hovertemplate="%{label}<br>%{customdata}<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(**LAYOUT_BASE, title="Composição da carga tributária atual", height=340)
    return fig


def grafico_evolucao_transicao(ctx: ContextoCalculo) -> go.Figure:
    """Linha dupla: carga atual vs. carga IVA ano a ano (2026-2033)."""
    anos = list(range(2026, 2034))
    carga_atual_pct, carga_iva_pct = [], []
    for ano in anos:
        aliquotas = get_aliquotas_ano(ano, ctx.setor)
        reducao = get_reducao_icms_iss(ano)
        atual = ctx.pis_cofins + ctx.icms * (Decimal("1") - reducao) + ctx.iss * (Decimal("1") - reducao)
        carga_atual_pct.append(float(atual * 100))
        carga_iva_pct.append(float(aliquotas["total"] * 100))

    indice_cruzamento = None
    for i in range(1, len(anos)):
        antes = carga_atual_pct[i - 1] - carga_iva_pct[i - 1]
        depois = carga_atual_pct[i] - carga_iva_pct[i]
        if antes >= 0 and depois < 0:
            indice_cruzamento = i
            break

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=anos, y=carga_atual_pct, mode="lines+markers", name="Carga Atual",
            line=dict(color=CORES["preto"], width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=anos, y=carga_iva_pct, mode="lines+markers", name="Carga IVA",
            line=dict(color=CORES["verde"], width=2),
        )
    )

    if indice_cruzamento is not None:
        anos_pos = anos[indice_cruzamento - 1:]
        atual_pos = carga_atual_pct[indice_cruzamento - 1:]
        iva_pos = carga_iva_pct[indice_cruzamento - 1:]
        fig.add_trace(
            go.Scatter(
                x=anos_pos, y=atual_pos, mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=anos_pos, y=iva_pos, mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(46,139,87,0.2)",
                showlegend=False, hoverinfo="skip",
            )
        )
        fig.add_annotation(
            x=anos[indice_cruzamento], y=carga_iva_pct[indice_cruzamento],
            text="Break-even", showarrow=True, arrowhead=2,
        )

    fig.update_layout(
        **LAYOUT_BASE,
        title="Evolução da transição 2026-2033",
        yaxis=dict(title="Alíquota efetiva", ticksuffix="%", tickformat=",.2f"),
        xaxis=dict(title="Ano", dtick=1),
        height=340,
    )
    return fig


def grafico_dentro_fora(resultado_df: dict) -> go.Figure:
    """Barras verticais: IBS/CBS por dentro vs. por fora (Modo Simples)."""
    dentro = resultado_df["dentro"]["tributo"]
    fora = resultado_df["fora"]["tributo"]
    vantajoso = resultado_df["vantajoso"]

    cor_dentro = CORES["verde_escuro"] if vantajoso == "dentro" else CORES["cinza_claro"]
    cor_fora = CORES["verde_escuro"] if vantajoso == "fora" else CORES["cinza_claro"]

    fig = go.Figure(
        go.Bar(
            x=["Por dentro", "Por fora"], y=[float(dentro), float(fora)],
            marker=dict(color=[cor_dentro, cor_fora]),
            text=[fmt_moeda(dentro), fmt_moeda(fora)], textposition="outside",
        )
    )

    diferenca = abs(float(fora) - float(dentro))
    maior = max(float(dentro), float(fora))
    menor = min(float(dentro), float(fora))
    fig.add_hline(y=menor, line_dash="dot", line_color=CORES["cinza_medio"])
    fig.add_annotation(
        x=0.5, xref="paper", y=maior, yshift=20,
        text=f"Diferença: {fmt_moeda(diferenca)}", showarrow=False,
    )

    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(
            text=(
                "IBS/CBS: Por dentro vs. Por fora<br>"
                "<sup>Por dentro = Preço × alíquota / (1 + alíquota) · "
                "Por fora = Preço × alíquota</sup>"
            )
        ),
        yaxis_title="R$",
        height=340,
    )
    return fig
