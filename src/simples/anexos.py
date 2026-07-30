"""Tabelas do Simples Nacional (CGSN 140/2018) — Anexos I a V.

Armazena as faixas oficiais de alíquota nominal e valor a deduzir por
anexo, e calcula a alíquota efetiva pela fórmula do Art. 18 §1º da
LC 123/2006: (RBT12 × alíquota nominal − valor a deduzir) / RBT12.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Dict, List, Optional

D = Decimal

RBT12_TETO = D("4800000.00")


class Anexo(str, Enum):
    I = "I"  # Comércio
    II = "II"  # Indústria
    III = "III"  # Serviços (Fator R >= 28%)
    IV = "IV"  # Serviços específicos (limpeza, vigilância, obras, advocacia)
    V = "V"  # Serviços alta tributação (Fator R < 28%)


@dataclass(frozen=True)
class FaixaSimples:
    numero: int
    limite_inferior: Decimal
    limite_superior: Decimal
    aliquota_nominal: Decimal
    valor_deduzir: Decimal


# Faixas de RBT12 — idênticas para os 5 anexos, só mudam alíquota/dedução.
_LIMITES = [
    (D("0"), D("180000.00")),
    (D("180000.01"), D("360000.00")),
    (D("360000.01"), D("720000.00")),
    (D("720000.01"), D("1800000.00")),
    (D("1800000.01"), D("3600000.00")),
    (D("3600000.01"), RBT12_TETO),
]


def _montar_tabela(aliquotas_deducoes: List[tuple]) -> List[FaixaSimples]:
    return [
        FaixaSimples(i + 1, inferior, superior, nominal, deduzir)
        for i, ((inferior, superior), (nominal, deduzir)) in enumerate(
            zip(_LIMITES, aliquotas_deducoes)
        )
    ]


TABELAS_SIMPLES: Dict[Anexo, List[FaixaSimples]] = {
    Anexo.I: _montar_tabela([
        (D("0.0400"), D("0.00")),
        (D("0.0730"), D("5940.00")),
        (D("0.0950"), D("13860.00")),
        (D("0.1070"), D("22500.00")),
        (D("0.1430"), D("87300.00")),
        (D("0.1900"), D("378000.00")),
    ]),
    Anexo.II: _montar_tabela([
        (D("0.0450"), D("0.00")),
        (D("0.0780"), D("5940.00")),
        (D("0.1000"), D("13860.00")),
        (D("0.1120"), D("22500.00")),
        (D("0.1470"), D("85500.00")),
        (D("0.3000"), D("720000.00")),
    ]),
    Anexo.III: _montar_tabela([
        (D("0.0600"), D("0.00")),
        (D("0.1120"), D("9360.00")),
        (D("0.1350"), D("17640.00")),
        (D("0.1600"), D("35640.00")),
        (D("0.2100"), D("125640.00")),
        (D("0.3300"), D("648000.00")),
    ]),
    Anexo.IV: _montar_tabela([
        (D("0.0450"), D("0.00")),
        (D("0.0900"), D("8100.00")),
        (D("0.1020"), D("12420.00")),
        (D("0.1400"), D("39780.00")),
        (D("0.2200"), D("183780.00")),
        (D("0.3300"), D("828000.00")),
    ]),
    Anexo.V: _montar_tabela([
        (D("0.1550"), D("0.00")),
        (D("0.1800"), D("4500.00")),
        (D("0.1950"), D("9900.00")),
        (D("0.2050"), D("17100.00")),
        (D("0.2300"), D("62100.00")),
        (D("0.3050"), D("540000.00")),
    ]),
}


def obter_faixa(rbt12: Decimal, anexo: Anexo) -> FaixaSimples:
    """Retorna a faixa aplicável para o RBT12 informado no anexo dado."""
    if rbt12 < D("0"):
        raise ValueError("rbt12 não pode ser negativo")
    if rbt12 > RBT12_TETO:
        raise ValueError(f"rbt12 acima do teto do Simples Nacional ({RBT12_TETO})")
    for faixa in TABELAS_SIMPLES[anexo]:
        if faixa.limite_inferior <= rbt12 <= faixa.limite_superior:
            return faixa
    raise ValueError(f"nenhuma faixa encontrada para rbt12={rbt12} no {anexo}")


def calcular_aliquota_efetiva(rbt12: Decimal, anexo: Anexo) -> Decimal:
    """Fórmula oficial CGSN: (RBT12 × alíquota nominal − valor a deduzir) / RBT12."""
    if rbt12 <= D("0"):
        raise ValueError("rbt12 deve ser maior que zero")
    faixa = obter_faixa(rbt12, anexo)
    bruta = (rbt12 * faixa.aliquota_nominal - faixa.valor_deduzir) / rbt12
    efetiva = bruta.quantize(D("0.0001"), rounding=ROUND_HALF_UP)
    return max(efetiva, D("0.0000"))


def determinar_anexo_por_fator_r(fator_r: Optional[Decimal]) -> Anexo:
    """Fator R = folha de pagamento últimos 12 meses / RBT12."""
    if fator_r is None or fator_r >= D("0.28"):
        return Anexo.III
    return Anexo.V
