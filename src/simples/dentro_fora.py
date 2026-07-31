"""IBS/CBS por dentro (modelo DAS) vs por fora (padrão LC 214), ancorado
em dados reais do extrato PGDAS-D — não estimativa manual.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from src.parser.normalizador import DadosNormalizados
from src.simples.anexos import calcular_aliquota_efetiva

D = Decimal
TOLERANCIA = D("0.01")
ALIQUOTA_ALERTA_MIGRACAO = D("0.15")


@dataclass(frozen=True)
class ResultadoDentroFora:
    # Dados de entrada
    receita_bruta: Decimal
    aliquota_efetiva: Decimal

    # Por fora — padrão LC 214 [Art. 14]
    base_por_fora: Decimal
    tributo_por_fora: Decimal
    preco_final_por_fora: Decimal

    # Por dentro — modelo DAS atual
    base_por_dentro: Decimal
    tributo_por_dentro: Decimal
    preco_final_por_dentro: Decimal

    # Comparativo
    diferenca_tributo: Decimal
    diferenca_percentual: Decimal
    vantajoso: str

    # Impacto anual (extrapolado)
    economia_anual_estimada: Decimal

    # Observações para o operador
    observacoes: List[str]


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def calcular_dentro_fora(receita_bruta: Decimal, aliquota_efetiva: Decimal) -> ResultadoDentroFora:
    """Calcula IBS/CBS por dentro vs por fora.

    Por fora [padrão LC 214]: tributo = receita × aliquota, base = receita,
    preço final = receita + tributo.
    Por dentro [modelo DAS]: tributo = receita × aliquota / (1 + aliquota),
    base = receita - tributo, preço final = receita (tributo já incluso).
    """
    if receita_bruta <= D("0"):
        raise ValueError("receita_bruta deve ser maior que zero")
    if aliquota_efetiva < D("0"):
        raise ValueError("aliquota_efetiva não pode ser negativa")

    base_por_fora = _q(receita_bruta)
    tributo_por_fora = _q(receita_bruta * aliquota_efetiva)
    preco_final_por_fora = _q(receita_bruta + tributo_por_fora)

    tributo_por_dentro = _q(receita_bruta * aliquota_efetiva / (1 + aliquota_efetiva))
    base_por_dentro = _q(receita_bruta - tributo_por_dentro)
    preco_final_por_dentro = _q(receita_bruta)

    diferenca_tributo = _q(tributo_por_fora - tributo_por_dentro)
    if tributo_por_dentro > D("0"):
        diferenca_percentual = _q(diferenca_tributo / tributo_por_dentro * 100)
    else:
        diferenca_percentual = D("0.00")

    if abs(diferenca_tributo) <= TOLERANCIA:
        vantajoso = "equivalente"
    elif tributo_por_fora < tributo_por_dentro:
        vantajoso = "por_fora"
    else:
        vantajoso = "por_dentro"

    economia_anual_estimada = _q(diferenca_tributo * 12)

    observacoes = [
        f"Tributo por fora: R$ {tributo_por_fora:.2f} | Tributo por dentro: "
        f"R$ {tributo_por_dentro:.2f} | Diferença: R$ {diferenca_tributo:.2f} "
        f"({diferenca_percentual:.2f}%).",
    ]
    if vantajoso == "por_fora":
        observacoes.append(
            f"Por fora é mais vantajoso: tributo menor em R$ {diferenca_tributo:.2f} "
            f"({diferenca_percentual:.2f}%)."
        )
    elif vantajoso == "por_dentro":
        observacoes.append(
            f"Por dentro é mais vantajoso: tributo menor em R$ {diferenca_tributo:.2f} "
            f"({diferenca_percentual:.2f}%)."
        )
    else:
        observacoes.append(
            "Diferença inferior a R$ 0,01 — regimes equivalentes para esta alíquota."
        )
    observacoes.append(
        f"Economia anual estimada: R$ {economia_anual_estimada:.2f} (diferença × 12)."
    )
    if aliquota_efetiva > ALIQUOTA_ALERTA_MIGRACAO:
        observacoes.append(
            "Alíquota efetiva acima de 15% — avaliar migração para regime regular IBS/CBS."
        )

    return ResultadoDentroFora(
        receita_bruta=_q(receita_bruta),
        aliquota_efetiva=aliquota_efetiva,
        base_por_fora=base_por_fora,
        tributo_por_fora=tributo_por_fora,
        preco_final_por_fora=preco_final_por_fora,
        base_por_dentro=base_por_dentro,
        tributo_por_dentro=tributo_por_dentro,
        preco_final_por_dentro=preco_final_por_dentro,
        diferenca_tributo=diferenca_tributo,
        diferenca_percentual=diferenca_percentual,
        vantajoso=vantajoso,
        economia_anual_estimada=economia_anual_estimada,
        observacoes=observacoes,
    )


def calcular_dentro_fora_extrato(dados: DadosNormalizados, rbt12: Decimal) -> ResultadoDentroFora:
    """Atalho que usa o anexo predominante identificado pelo normalizador."""
    aliquota_efetiva = calcular_aliquota_efetiva(rbt12, dados.anexo_predominante)
    return calcular_dentro_fora(rbt12, aliquota_efetiva)
