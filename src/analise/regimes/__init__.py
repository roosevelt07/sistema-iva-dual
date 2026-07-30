"""Contrato comum dos módulos de comparação de regime.

Define `CenarioUnico` e `ResultadoCenarios`, além de helpers
compartilhados (`_montar_cenario`, `_cenario_b_regime_regular`) usados
por `simples.py`, `presumido.py` e `real.py`. Cada um desses módulos
expõe uma única função pública: `calcular(ctx) -> ResultadoCenarios`.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.analise.config_lc214 import Regime
from src.analise.credito import calcular_credito
from src.analise.formulario import ContextoCalculo

D = Decimal


@dataclass
class CenarioUnico:
    nome: str
    carga_bruta: Decimal
    credito_aproveitado: Decimal
    carga_liquida: Decimal
    aliquota_efetiva: Decimal
    detalhes: dict


@dataclass
class ResultadoCenarios:
    cenario_a: CenarioUnico  # regime atual
    cenario_b: CenarioUnico  # regime regular IBS/CBS
    delta: Decimal  # cenario_a.carga_liquida - cenario_b.carga_liquida
    regime: Regime
    faturamento: Decimal


def _montar_cenario(
    nome: str,
    carga_bruta: Decimal,
    credito_aproveitado: Decimal,
    faturamento: Decimal,
    detalhes: dict,
) -> CenarioUnico:
    carga_bruta = carga_bruta.quantize(D("0.01"), rounding=ROUND_HALF_UP)
    credito_aproveitado = credito_aproveitado.quantize(D("0.01"), rounding=ROUND_HALF_UP)
    carga_liquida = max(D("0.00"), carga_bruta - credito_aproveitado)

    if faturamento == D("0"):
        aliquota_efetiva = D("0.0000")
    else:
        aliquota_efetiva = (carga_liquida / faturamento).quantize(D("0.0001"), rounding=ROUND_HALF_UP)

    return CenarioUnico(
        nome=nome,
        carga_bruta=carga_bruta,
        credito_aproveitado=credito_aproveitado,
        carga_liquida=carga_liquida,
        aliquota_efetiva=aliquota_efetiva,
        detalhes=detalhes,
    )


def _cenario_b_regime_regular(ctx: ContextoCalculo) -> CenarioUnico:
    """Cenário B — migrar para o regime regular IBS/CBS. Idêntico nos 3 módulos."""
    carga_bruta_b = ctx.faturamento * ctx.ibs_cbs_total
    credito_b = calcular_credito(ctx).total
    detalhes = {
        "ibs_cbs_bruto": carga_bruta_b.quantize(D("0.01"), rounding=ROUND_HALF_UP),
        "credito_entrada": credito_b,
        "credito_regime_normal": ctx.credito_entrada_regime_normal,
        "credito_simples": ctx.credito_entrada_simples,
    }
    return _montar_cenario("Regime regular IBS/CBS", carga_bruta_b, credito_b, ctx.faturamento, detalhes)
