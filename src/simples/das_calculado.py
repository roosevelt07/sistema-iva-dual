"""DAS combinando múltiplas atividades do Simples Nacional em Anexos distintos.

Um mesmo optante pode ter receita em mais de um Anexo simultaneamente
(ex.: revenda tributada + revenda com ICMS-ST + prestação de serviço).
O DAS total é a soma do DAS de cada atividade — cada uma usando a
alíquota efetiva do seu próprio Anexo sobre o RBT12 da empresa (que é
único, não por atividade), nunca uma alíquota combinada única.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List

from src.simples.anexos import Anexo, calcular_aliquota_efetiva

D = Decimal


@dataclass(frozen=True)
class AtividadeReceita:
    nome: str
    anexo: Anexo
    receita_atividade: Decimal
    com_st_ou_monofasico: bool = False


@dataclass(frozen=True)
class ResultadoDAS:
    rbt12: Decimal
    atividades: List[AtividadeReceita]
    das_por_atividade: Dict[str, Decimal]
    das_total: Decimal
    aliquota_efetiva_media: Decimal


def calcular_das_multiplas_atividades(
    rbt12: Decimal,
    atividades: List[AtividadeReceita],
) -> ResultadoDAS:
    """Soma o DAS de cada atividade, cada uma na alíquota efetiva do seu Anexo."""
    if not atividades:
        raise ValueError("é necessário informar ao menos uma atividade")

    das_por_atividade: Dict[str, Decimal] = {}
    for atividade in atividades:
        aliquota = calcular_aliquota_efetiva(rbt12, atividade.anexo)
        das_atividade = (atividade.receita_atividade * aliquota).quantize(
            D("0.01"), rounding=ROUND_HALF_UP
        )
        das_por_atividade[atividade.nome] = das_atividade

    das_total = sum(das_por_atividade.values(), D("0.00"))
    soma_receitas = sum((a.receita_atividade for a in atividades), D("0.00"))
    if soma_receitas > D("0"):
        aliquota_efetiva_media = (das_total / soma_receitas).quantize(
            D("0.0001"), rounding=ROUND_HALF_UP
        )
    else:
        aliquota_efetiva_media = D("0.0000")

    return ResultadoDAS(
        rbt12=rbt12,
        atividades=atividades,
        das_por_atividade=das_por_atividade,
        das_total=das_total,
        aliquota_efetiva_media=aliquota_efetiva_media,
    )


def calcular_das_atividade_unica(
    rbt12: Decimal,
    receita: Decimal,
    anexo: Anexo,
) -> Decimal:
    """Atalho para cliente com uma única atividade — delega para
    `calcular_das_multiplas_atividades` com lista de 1 item."""
    atividade = AtividadeReceita(nome="atividade_unica", anexo=anexo, receita_atividade=receita)
    resultado = calcular_das_multiplas_atividades(rbt12, [atividade])
    return resultado.das_total
