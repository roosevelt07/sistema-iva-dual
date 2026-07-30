"""Testes do módulo `parser.pgdas_parser`.

Testes 1-18 usam o PDF real em `tests/fixtures/pgdas_exemplo.pdf`.
Teste 19 (estrutura essencial ausente) usa `parsear_texto_pgdas` com uma
string sem a linha de CNPJ, sem precisar de um segundo PDF malformado.
"""

import os
from decimal import Decimal as D

import pytest

from src.parser.pgdas_parser import PGDASParserError, parsear_pgdas, parsear_texto_pgdas

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "pgdas_exemplo.pdf"
)


@pytest.fixture(scope="module")
def extrato():
    if not os.path.isfile(FIXTURE):
        pytest.skip("tests/fixtures/pgdas_exemplo.pdf ainda não foi fornecido")
    return parsear_pgdas(FIXTURE)


def test_cnpj_basico(extrato):
    assert extrato.cnpj_basico == "16.682.120"


def test_razao_social_contem_nome(extrato):
    assert "S & L LOCACOES" in extrato.razao_social


def test_periodo_apuracao(extrato):
    assert extrato.periodo_apuracao == "04/2026"


def test_rpa(extrato):
    assert extrato.rpa == D("139182.41")


def test_rbt12(extrato):
    assert extrato.rbt12 == D("1502383.95")


def test_fator_r_nao_se_aplica_vira_none(extrato):
    assert extrato.fator_r is None


def test_sublimite_receita_anual(extrato):
    assert extrato.sublimite_receita_anual == D("3600000.00")


def test_tres_blocos_de_atividade(extrato):
    assert len(extrato.blocos_atividade) == 3


def test_receita_bloco_0(extrato):
    assert extrato.blocos_atividade[0].receita_bruta_informada == D("54392.65")


def test_bloco_1_com_substituicao_tributaria(extrato):
    assert extrato.blocos_atividade[1].com_substituicao_tributaria is True


def test_bloco_1_tributos_st(extrato):
    assert extrato.blocos_atividade[1].tributos_st == ["ICMS"]


def test_bloco_1_com_tributacao_monofasica(extrato):
    assert extrato.blocos_atividade[1].com_tributacao_monofasica is True


def test_bloco_1_tributos_monofasicos(extrato):
    assert extrato.blocos_atividade[1].tributos_monofasicos == ["COFINS", "PIS"]


def test_das_total(extrato):
    assert extrato.das_total == D("14477.63")


def test_das_icms(extrato):
    assert extrato.das_icms == D("1676.82")


def test_das_iss(extrato):
    assert extrato.das_iss == D("2722.90")


def test_soma_totais_dos_blocos_aproxima_das_total(extrato):
    soma = sum((b.total for b in extrato.blocos_atividade), D("0.00"))
    assert abs(soma - extrato.das_total) <= D("0.01")


def test_pdf_inexistente_levanta_pgdas_parser_error():
    with pytest.raises(PGDASParserError):
        parsear_pgdas("/caminho/que/nao/existe.pdf")


def test_texto_sem_cnpj_levanta_pgdas_parser_error():
    texto_sem_cnpj = """Informações do Contribuinte
Nome Empresarial: EMPRESA TESTE LTDA
Data de Abertura: 01/01/2020 Regime de Apuração: Competência
"""
    with pytest.raises(PGDASParserError):
        parsear_texto_pgdas(texto_sem_cnpj)
