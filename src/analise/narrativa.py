"""Texto interpretativo para o operador.

Traduz os resultados numéricos da análise em um texto explicativo,
em linguagem acessível, para apoiar a decisão do operador. Só
formatação — nenhum cálculo novo.
"""

from src.analise.decisao import ResultadoAnalise
from src.analise.formatters import fmt_moeda, fmt_percentual

_REGIME_LABELS = {
    "simples": "Simples Nacional",
    "presumido": "Lucro Presumido",
    "real": "Lucro Real",
}

_SETOR_LABELS = {
    "padrao": "padrão",
    "educacao": "educação",
    "saude": "saúde",
    "dispositivos_med": "dispositivos médicos",
    "acessibilidade": "acessibilidade",
    "medicamentos": "medicamentos",
    "alimentos": "alimentos",
    "higiene_baixa_renda": "higiene para baixa renda",
    "agropecuario": "agropecuário",
    "cultural": "cultural",
    "desportivo": "desportivo",
    "seguranca_nac": "segurança nacional",
}


def gerar_narrativa(resultado: ResultadoAnalise) -> str:
    """Única função pública do módulo."""
    ctx = resultado.ctx
    cenario_a = resultado.cenarios.cenario_a
    cenario_b = resultado.cenarios.cenario_b

    regime_label = _REGIME_LABELS[ctx.regime.value]
    setor_label = _SETOR_LABELS[ctx.setor.value]

    contexto = (
        f"Cliente no {regime_label}, setor {setor_label}, "
        f"faturamento de {fmt_moeda(ctx.faturamento)}, simulação para {ctx.ano}."
    )

    carga_atual = (
        f"Carga atual estimada em {fmt_moeda(cenario_a.carga_liquida)} "
        f"({fmt_percentual(cenario_a.aliquota_efetiva * 100)} efetivo)."
    )

    carga_regular = (
        f"No regime regular do IBS/CBS a carga líquida seria {fmt_moeda(cenario_b.carga_liquida)} "
        f"({fmt_percentual(cenario_b.aliquota_efetiva * 100)} efetivo), considerando "
        f"{fmt_moeda(cenario_b.credito_aproveitado)} de crédito de entrada aproveitado."
    )

    if resultado.delta_absoluto > 0:
        delta_frase = (
            f"A migração representa economia de {fmt_moeda(resultado.delta_absoluto)} "
            f"({fmt_percentual(resultado.delta_percentual)})."
        )
    elif resultado.delta_absoluto < 0:
        delta_frase = (
            f"A migração representa aumento de {fmt_moeda(abs(resultado.delta_absoluto))} "
            f"({fmt_percentual(abs(resultado.delta_percentual))})."
        )
    else:
        delta_frase = "A migração resulta em sem variação de carga tributária entre os regimes."

    recomendacao_frase = (
        "Recomendação: migrar para o regime regular do IBS/CBS."
        if resultado.recomendacao == "MIGRAR_REGIME_REGULAR"
        else "Recomendação: manter o regime atual."
    )

    alertas_frases = " ".join(f"Atenção: {alerta}" for alerta in resultado.alertas)

    partes = [contexto, carga_atual, carga_regular, delta_frase, recomendacao_frase]
    if alertas_frases:
        partes.append(alertas_frases)
    return " ".join(partes)
