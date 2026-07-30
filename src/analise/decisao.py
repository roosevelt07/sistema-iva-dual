"""Delta cenários + recomendação final.

Roteia `ContextoCalculo` para o módulo de regime correto, consolida o
crédito de entrada e a comparação de cenários, e produz a recomendação
final junto com os alertas relevantes para o operador. Não recalcula
nada — só roteia, consolida e formata mensagens.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from src.analise.config_lc214 import FluxoComercial, Regime
from src.analise.credito import CreditoEntrada, calcular_credito
from src.analise.formulario import ContextoCalculo
from src.analise.regimes import ResultadoCenarios, presumido, real, simples

D = Decimal

_MODULOS_POR_REGIME = {
    Regime.SIMPLES: simples,
    Regime.PRESUMIDO: presumido,
    Regime.REAL: real,
}


@dataclass
class ResultadoAnalise:
    ctx: ContextoCalculo
    cenarios: ResultadoCenarios
    credito: CreditoEntrada
    recomendacao: str
    delta_absoluto: Decimal
    delta_percentual: Decimal
    alertas: List[str]


def analisar(ctx: ContextoCalculo) -> ResultadoAnalise:
    """Única função pública do módulo."""
    modulo = _MODULOS_POR_REGIME[ctx.regime]
    cenarios = modulo.calcular(ctx)
    credito = calcular_credito(ctx)

    recomendacao = "MIGRAR_REGIME_REGULAR" if cenarios.delta > D("0") else "MANTER_REGIME_ATUAL"

    delta_absoluto = cenarios.delta.quantize(D("0.01"), rounding=ROUND_HALF_UP)

    if cenarios.cenario_a.carga_liquida > D("0"):
        delta_percentual = (
            cenarios.delta / cenarios.cenario_a.carga_liquida * D("100")
        ).quantize(D("0.01"), rounding=ROUND_HALF_UP)
    else:
        delta_percentual = D("0.00")

    alertas: List[str] = []
    if ctx.alerta_placeholder_senado:
        alertas.append(
            "Alíquotas de referência 2027+ são estimativas — aguardando Resolução do Senado."
        )
    if ctx.alerta_limite_simples:
        alertas.append(
            "Faturamento acima do limite do Simples (R$ 4,8M) — verifique enquadramento."
        )
    if abs(cenarios.delta) < D("500"):
        alertas.append(
            "Delta inferior a R$ 500,00 — diferença não é material, considere o custo de conformidade."
        )
    if ctx.fluxo == FluxoComercial.MISTO and recomendacao == "MANTER_REGIME_ATUAL":
        alertas.append(
            f"Cliente tem {ctx.percentual_b2b * 100:.0f}% de vendas B2B — clientes podem exigir "
            "regime regular para crédito pleno a partir de 2029."
        )

    return ResultadoAnalise(
        ctx=ctx,
        cenarios=cenarios,
        credito=credito,
        recomendacao=recomendacao,
        delta_absoluto=delta_absoluto,
        delta_percentual=delta_percentual,
        alertas=alertas,
    )
