"""Módulo 2: Lucro Presumido vs. regime regular (IBS/CBS).

Simula o impacto da LC 214/2025 para contribuintes tributados pelo
Lucro Presumido, comparando a permanência no regime com a migração
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
    pis_cofins = ctx.faturamento * ctx.pis_cofins
    icms = ctx.faturamento * ctx.icms * (D("1") - ctx.reducao_icms_iss_ano)
    iss = ctx.faturamento * ctx.iss * (D("1") - ctx.reducao_icms_iss_ano)
    carga_bruta_a = pis_cofins + icms + iss

    detalhes_a = {
        "pis_cofins": pis_cofins.quantize(D("0.01")),
        "icms": icms.quantize(D("0.01")),
        "iss": iss.quantize(D("0.01")),
        "reducao_icms_iss_aplicada": ctx.reducao_icms_iss_ano,
    }
    cenario_a = _montar_cenario("Lucro Presumido", carga_bruta_a, D("0.00"), ctx.faturamento, detalhes_a)
    cenario_b = _cenario_b_regime_regular(ctx)

    return ResultadoCenarios(
        cenario_a=cenario_a,
        cenario_b=cenario_b,
        delta=cenario_a.carga_liquida - cenario_b.carga_liquida,
        regime=ctx.regime,
        faturamento=ctx.faturamento,
    )
