"""Testes de `config_lc214`.

Valida as alíquotas de IBS/CBS por ano e por setor contra os valores
previstos nos Art. 128, 343, 344 e 346 da LC 214/2025.
"""

from decimal import Decimal as D

import pytest

from src.analise.config_lc214 import (
    CRONOGRAMA_REDUCAO_ICMS_ISS,
    REDUCAO_SETOR,
    Setor,
    get_aliquotas_ano,
    get_reducao_icms_iss,
)


def test_aliquotas_2026():
    # Art. 343 e 346 — CBS=0,9%, IBS=0,1% (setor padrão, sem redução)
    resultado = get_aliquotas_ano(2026, Setor.PADRAO)
    assert resultado["cbs"] == D("0.009")
    assert resultado["ibs"] == D("0.001")
    assert resultado["fase"] == "2026"


def test_aliquotas_2027():
    # Art. 344 e 347 — IBS=0,1% total, CBS=8,7% (8,8%-0,1%)
    resultado = get_aliquotas_ano(2027, Setor.PADRAO)
    assert resultado["ibs"] == D("0.001")
    assert resultado["cbs"] == D("0.087")


def test_aliquotas_2029_plena():
    # Art. 18, Art. 361-365 — alíquota de referência plena
    resultado = get_aliquotas_ano(2029, Setor.PADRAO)
    assert resultado["cbs"] == D("0.088")
    assert resultado["ibs"] == D("0.177")
    assert resultado["total"] == D("0.265")


def test_reducao_setor_alimentos_2029():
    # Art. 128 — redução de 60% aplicada à alíquota, não à base de cálculo
    resultado = get_aliquotas_ano(2029, Setor.ALIMENTOS)
    assert resultado["total"] == D("0.265") * D("0.40")
    assert resultado["total"] == D("0.1060")


def test_reducao_icms_iss_cronograma():
    # Art. 501 — ICMS/ISS intocados até 2028, redução gradual a partir de 2029
    assert get_reducao_icms_iss(2026) == D("0.00")
    assert get_reducao_icms_iss(2027) == D("0.00")
    assert get_reducao_icms_iss(2028) == D("0.00")
    assert get_reducao_icms_iss(2029) == D("0.10")
    assert get_reducao_icms_iss(2032) == D("0.40")


def test_ano_fora_intervalo():
    with pytest.raises(ValueError):
        get_aliquotas_ano(2025)
    with pytest.raises(ValueError):
        get_aliquotas_ano(2034)


def test_todos_setores_reducao_60_ou_0():
    # Art. 128 — todos os 11 setores têm redução exatamente 60%; PADRAO tem 0%
    for setor in Setor:
        if setor == Setor.PADRAO:
            assert REDUCAO_SETOR[setor] == D("0.00")
        else:
            assert REDUCAO_SETOR[setor] == D("0.60")
