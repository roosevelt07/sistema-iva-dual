"""Lógica de crédito de entrada (Art. 47 LC 214).

Calcula o crédito de IBS/CBS apropriável sobre as aquisições do
contribuinte, conforme a não-cumulatividade plena prevista no
Art. 47 da LC 214/2025. Não calcula carga tributária — só crédito.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from src.analise.formulario import ContextoCalculo

D = Decimal


@dataclass
class CreditoEntrada:
    credito_fornecedor_normal: Decimal  # Art. 47 caput — crédito pleno
    credito_fornecedor_simples: Decimal  # Art. 47 §9º II — proporcional ao DAS
    credito_fornecedor_isento: Decimal  # Art. 49 — sempre zero
    compras_isento: Decimal  # rastreabilidade — nunca soma no cálculo
    total: Decimal  # credito_fornecedor_normal + credito_fornecedor_simples
    proporcao_sobre_faturamento: Decimal  # total / faturamento (indicador)
    observacoes: List[str]  # alertas/notas para o operador


def calcular_credito(ctx: ContextoCalculo) -> CreditoEntrada:
    """Única função pública do módulo."""
    credito_normal = (ctx.compras_regime_normal * ctx.ibs_cbs_total).quantize(
        D("0.01"), rounding=ROUND_HALF_UP
    )  # Art. 47 caput
    credito_simples = (ctx.compras_simples * ctx.aliquota_das_fornecedor).quantize(
        D("0.01"), rounding=ROUND_HALF_UP
    )  # Art. 47 §9º II
    credito_isento = D("0.00")  # Art. 49 — sempre zero, sem exceção

    total = credito_normal + credito_simples

    if ctx.faturamento == D("0"):
        proporcao = D("0.00")
    else:
        proporcao = (total / ctx.faturamento).quantize(D("0.01"), rounding=ROUND_HALF_UP)

    observacoes: List[str] = []
    if ctx.compras_isento > D("0"):
        observacoes.append(
            f"Compras de fornecedores isentos (R$ {ctx.compras_isento}) não geram "
            "crédito [Art. 49, LC 214]."
        )
    if ctx.aliquota_das_fornecedor == D("0.005"):
        observacoes.append(
            "Alíquota DAS do fornecedor usando estimativa padrão (0,5%) — confirme o valor real."
        )
    if ctx.fase == "2027-2028":
        observacoes.append(
            "Alíquotas de referência 2027-2028 são estimativas — Resolução do Senado não publicada."
        )
    if proporcao > D("0.30"):
        observacoes.append(
            "Crédito de entrada representa mais de 30% do faturamento — verifique consistência dos dados."
        )

    return CreditoEntrada(
        credito_fornecedor_normal=credito_normal,
        credito_fornecedor_simples=credito_simples,
        credito_fornecedor_isento=credito_isento,
        compras_isento=ctx.compras_isento,
        total=total,
        proporcao_sobre_faturamento=proporcao,
        observacoes=observacoes,
    )
