"""Testes do módulo `simples.dentro_fora`."""

import os
from decimal import Decimal as D

import pytest

from src.parser.normalizador import normalizar_extrato
from src.parser.pgdas_parser import parsear_pgdas
from src.simples.dentro_fora import calcular_dentro_fora, calcular_dentro_fora_extrato

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "pgdas_exemplo.pdf"
)


def test_por_fora_e_por_dentro_receita_1000_aliquota_10_por_cento():
    resultado = calcular_dentro_fora(D("1000"), D("0.10"))
    assert resultado.tributo_por_fora == D("100.00")
    assert resultado.tributo_por_dentro == D("90.91")
    assert resultado.vantajoso == "por_dentro"


def test_precos_finais():
    resultado = calcular_dentro_fora(D("1000"), D("0.10"))
    assert resultado.preco_final_por_fora == D("1100.00")
    assert resultado.preco_final_por_dentro == D("1000.00")


def test_diferenca_tributo():
    resultado = calcular_dentro_fora(D("1000"), D("0.10"))
    assert resultado.diferenca_tributo == D("9.09")


def test_economia_anual_estimada():
    resultado = calcular_dentro_fora(D("1000"), D("0.10"))
    assert resultado.economia_anual_estimada == D("9.09") * 12
    assert resultado.economia_anual_estimada == D("109.08")


def test_aliquota_muito_pequena_vantajoso_equivalente():
    resultado = calcular_dentro_fora(D("1000"), D("0.0001"))
    assert resultado.vantajoso == "equivalente"


def test_receita_zero_ou_negativa_levanta_value_error():
    with pytest.raises(ValueError):
        calcular_dentro_fora(D("0"), D("0.10"))
    with pytest.raises(ValueError):
        calcular_dentro_fora(D("-100"), D("0.10"))


def test_aliquota_negativa_levanta_value_error():
    with pytest.raises(ValueError):
        calcular_dentro_fora(D("1000"), D("-0.01"))


def test_aliquota_zero():
    resultado = calcular_dentro_fora(D("1000"), D("0"))
    assert resultado.tributo_por_fora == D("0.00")
    assert resultado.tributo_por_dentro == D("0.00")
    assert resultado.vantajoso == "equivalente"


def test_observacoes_nunca_vazia_tem_pelo_menos_2_itens():
    resultado = calcular_dentro_fora(D("1000"), D("0.10"))
    assert len(resultado.observacoes) >= 2


def test_calcular_dentro_fora_extrato_com_dados_reais():
    if not os.path.isfile(FIXTURE):
        pytest.skip("tests/fixtures/pgdas_exemplo.pdf ainda não foi fornecido")
    extrato = parsear_pgdas(FIXTURE)
    dados = normalizar_extrato(extrato)
    resultado = calcular_dentro_fora_extrato(dados, extrato.rbt12)
    assert resultado.receita_bruta == extrato.rbt12
    assert resultado.vantajoso in ("por_fora", "por_dentro", "equivalente")


def test_aliquota_acima_de_15_por_cento_gera_observacao_de_migracao():
    resultado = calcular_dentro_fora(D("1000"), D("0.20"))
    assert any("migração" in obs for obs in resultado.observacoes)


def test_valores_arredondados_em_duas_casas():
    resultado = calcular_dentro_fora(D("1234.5678"), D("0.0925"))
    campos_decimais = [
        resultado.receita_bruta,
        resultado.base_por_fora,
        resultado.tributo_por_fora,
        resultado.preco_final_por_fora,
        resultado.base_por_dentro,
        resultado.tributo_por_dentro,
        resultado.preco_final_por_dentro,
        resultado.diferenca_tributo,
        resultado.diferenca_percentual,
        resultado.economia_anual_estimada,
    ]
    for valor in campos_decimais:
        assert valor == valor.quantize(D("0.01"))


def test_tributo_por_dentro_sempre_menor_que_por_fora_para_aliquota_positiva():
    for aliquota in (D("0.01"), D("0.05"), D("0.10"), D("0.265"), D("0.50")):
        resultado = calcular_dentro_fora(D("100000"), aliquota)
        assert resultado.tributo_por_dentro < resultado.tributo_por_fora


def test_vantajoso_so_pode_ser_um_dos_tres_valores():
    for aliquota in (D("0"), D("0.0001"), D("0.10"), D("0.30")):
        resultado = calcular_dentro_fora(D("50000"), aliquota)
        assert resultado.vantajoso in ("por_fora", "por_dentro", "equivalente")
