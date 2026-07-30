"""Testes do módulo `simples.anexos`."""

from decimal import Decimal as D

import pytest

from src.simples.anexos import (
    TABELAS_SIMPLES,
    Anexo,
    calcular_aliquota_efetiva,
    determinar_anexo_por_fator_r,
    obter_faixa,
)


def test_anexo_i_rbt12_1502383_95_cai_na_faixa_4():
    faixa = obter_faixa(D("1502383.95"), Anexo.I)
    assert faixa.numero == 4
    assert calcular_aliquota_efetiva(D("1502383.95"), Anexo.I) == D("0.0920")


def test_anexo_i_rbt12_100000_cai_na_faixa_1_sem_deducao():
    faixa = obter_faixa(D("100000"), Anexo.I)
    assert faixa.numero == 1
    assert calcular_aliquota_efetiva(D("100000"), Anexo.I) == D("0.0400")


def test_anexo_v_rbt12_4800000_cai_na_faixa_6():
    faixa = obter_faixa(D("4800000"), Anexo.V)
    assert faixa.numero == 6
    assert calcular_aliquota_efetiva(D("4800000"), Anexo.V) == D("0.1925")


def test_rbt12_acima_do_teto_levanta_value_error():
    with pytest.raises(ValueError):
        obter_faixa(D("4800000.01"), Anexo.I)


def test_rbt12_zero_ou_negativo_levanta_value_error():
    with pytest.raises(ValueError):
        calcular_aliquota_efetiva(D("0"), Anexo.I)
    with pytest.raises(ValueError):
        calcular_aliquota_efetiva(D("-1"), Anexo.I)


def test_fator_r_none_retorna_anexo_iii():
    assert determinar_anexo_por_fator_r(None) == Anexo.III


def test_fator_r_maior_igual_28_por_cento_retorna_anexo_iii():
    assert determinar_anexo_por_fator_r(D("0.30")) == Anexo.III
    assert determinar_anexo_por_fator_r(D("0.28")) == Anexo.III


def test_fator_r_menor_que_28_por_cento_retorna_anexo_v():
    assert determinar_anexo_por_fator_r(D("0.20")) == Anexo.V


def test_todos_os_anexos_tem_exatamente_6_faixas():
    for anexo in Anexo:
        assert len(TABELAS_SIMPLES[anexo]) == 6


def test_faixas_sao_contiguas_em_cada_anexo():
    for anexo in Anexo:
        faixas = TABELAS_SIMPLES[anexo]
        for atual, proxima in zip(faixas, faixas[1:]):
            assert atual.limite_superior == proxima.limite_inferior - D("0.01")


def test_calcular_aliquota_efetiva_nunca_negativa():
    for anexo in Anexo:
        for faixa in TABELAS_SIMPLES[anexo]:
            rbt12 = faixa.limite_superior
            assert calcular_aliquota_efetiva(rbt12, anexo) >= D("0.0000")
