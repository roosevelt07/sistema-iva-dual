"""Módulo 1: Simples Nacional vs. regime regular (IBS/CBS).

Simula o impacto da LC 214/2025 para contribuintes optantes pelo
Simples Nacional, comparando a permanência no regime com a migração
para o regime regular de apuração de IBS/CBS.
"""

from src.analise.formulario import ContextoCalculo
from src.analise.regimes import (
    D,
    ResultadoCenarios,
    _cenario_b_regime_regular,
    _montar_cenario,
)


def calcular(ctx: ContextoCalculo) -> ResultadoCenarios:
    carga_bruta_a = ctx.faturamento * (ctx.cbs_efetiva + ctx.ibs_efetiva)
    detalhes_a = {
        "ibs_cbs_das": carga_bruta_a.quantize(D("0.01")),
        "credito_entrada": D("0.00"),
        "observacao": "No Simples o crédito de entrada não é aproveitado [Art. 47 §9º I]",
    }
    cenario_a = _montar_cenario("Simples Nacional", carga_bruta_a, D("0.00"), ctx.faturamento, detalhes_a)
    cenario_b = _cenario_b_regime_regular(ctx)

    return ResultadoCenarios(
        cenario_a=cenario_a,
        cenario_b=cenario_b,
        delta=cenario_a.carga_liquida - cenario_b.carga_liquida,
        regime=ctx.regime,
        faturamento=ctx.faturamento,
    )
