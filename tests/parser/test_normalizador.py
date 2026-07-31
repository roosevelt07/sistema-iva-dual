"""Testes do módulo `parser.normalizador`.

Usa `tests/fixtures/pgdas_exemplo.pdf` (fixture fictícia — ver
`tests/parser/test_pgdas_parser.py`) como extrato base. Dois pontos do
enunciado original assumiam os valores do PDF real anterior à remediação
de segurança (que trocou o PDF por dados fictícios); ajustados aqui para
os valores atuais da fixture, com nota explicando a diferença. Dois testes
extras (marcados como "extra") cobrem, com dados sintéticos, comportamento
que a fixture atual não exercita sozinha: seleção do anexo predominante
quando o maior bloco não é o primeiro, e o alerta de Fator R.
"""

import dataclasses
import os
from decimal import Decimal as D

import pytest

from src.analise.config_lc214 import Regime
from src.parser.normalizador import normalizar_extrato
from src.parser.pgdas_parser import parsear_pgdas
from src.simples.anexos import Anexo

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "pgdas_exemplo.pdf")


@pytest.fixture(scope="module")
def extrato():
    if not os.path.isfile(FIXTURE):
        pytest.skip("tests/fixtures/pgdas_exemplo.pdf ainda não foi fornecido")
    return parsear_pgdas(FIXTURE)


def test_regime_atual_sempre_simples(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.dados_cliente.regime_atual == Regime.SIMPLES


def test_faturamento_anual_igual_rbt12(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.dados_cliente.faturamento_anual == extrato.rbt12


def test_uf_do_extrato(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.dados_cliente.uf == "PE"


def test_tres_atividades(extrato):
    resultado = normalizar_extrato(extrato)
    assert len(resultado.atividades) == 3


def test_atividade_0_anexo_i_revenda(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.atividades[0].anexo == Anexo.I


def test_atividade_2_anexo_iii_servico_fator_r_none(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.atividades[2].anexo == Anexo.III


def test_anexo_predominante(extrato):
    # O enunciado original assumia os valores do PDF real (serviço
    # 61.478,63 > revenda 54.392,65 > ST 23.311,13 => Anexo.III). A fixture
    # atual (fictícia, pós-remediação de segurança) tem valores diferentes:
    # bloco 0 (revenda, Anexo.I) = 50.000,00 é o maior, não o bloco 2
    # (serviço) = 30.000,00. A lógica de seleção pelo maior valor em si é
    # coberta de forma não trivial pelo teste
    # `test_extra_anexo_predominante_nao_e_sempre_o_primeiro` abaixo.
    resultado = normalizar_extrato(extrato)
    assert resultado.anexo_predominante == Anexo.I


def test_alerta_st_presente(extrato):
    resultado = normalizar_extrato(extrato)
    assert any("ST" in a for a in resultado.alertas_normalizacao)


def test_alerta_monofasico_presente(extrato):
    resultado = normalizar_extrato(extrato)
    assert any("monofásica" in a for a in resultado.alertas_normalizacao)


def test_alerta_desenquadramento_ausente(extrato):
    # rbt12 da fixture atual é 900.000,00 (era 1.502.383,95 no PDF real
    # original) — em ambos os casos, bem abaixo do limiar de alerta
    # (4.320.000,00), então o resultado esperado (alerta ausente) não muda.
    resultado = normalizar_extrato(extrato)
    assert not any("desenquadramento" in a for a in resultado.alertas_normalizacao)


def test_dados_cliente_instancia_valida_sem_erro(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.dados_cliente.faturamento_anual > D("0")


def test_percentual_b2b_default(extrato):
    resultado = normalizar_extrato(extrato)
    assert resultado.dados_cliente.percentual_b2b == D("0.50")


def test_compras_informadas_chegam_ao_dados_cliente(extrato):
    resultado = normalizar_extrato(
        extrato,
        compras_regime_normal=D("12345.67"),
        compras_simples=D("111.11"),
        compras_isento=D("222.22"),
    )
    assert resultado.dados_cliente.compras_fornecedor_regime_normal == D("12345.67")
    assert resultado.dados_cliente.compras_fornecedor_simples == D("111.11")
    assert resultado.dados_cliente.compras_fornecedor_isento == D("222.22")


def test_alerta_ano_2026(extrato):
    resultado = normalizar_extrato(extrato, ano_referencia=2026)
    assert any("2026" in a and "teste" in a for a in resultado.alertas_normalizacao)


def test_extra_anexo_predominante_nao_e_sempre_o_primeiro(extrato):
    blocos = list(extrato.blocos_atividade)
    blocos[0] = dataclasses.replace(blocos[0], receita_bruta_informada=D("1000.00"))
    blocos[2] = dataclasses.replace(blocos[2], receita_bruta_informada=D("999999.00"))
    extrato_sintetico = dataclasses.replace(extrato, blocos_atividade=blocos)

    resultado = normalizar_extrato(extrato_sintetico)
    assert resultado.anexo_predominante == Anexo.III


def test_extra_alerta_fator_r_dispara_quando_aplica(extrato):
    extrato_sintetico = dataclasses.replace(extrato, fator_r=D("0.15"))
    resultado = normalizar_extrato(extrato_sintetico)
    assert any("Fator R" in a for a in resultado.alertas_normalizacao)
