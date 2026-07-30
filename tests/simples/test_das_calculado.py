"""Testes do módulo `simples.das_calculado`."""

from decimal import Decimal as D

import pytest

from src.simples.anexos import Anexo, calcular_aliquota_efetiva
from src.simples.das_calculado import (
    AtividadeReceita,
    calcular_das_atividade_unica,
    calcular_das_multiplas_atividades,
)

RBT12_EXTRATO = D("1502383.95")


def _atividades_extrato_real():
    return [
        AtividadeReceita("Revenda tributada", Anexo.I, D("54392.65")),
        AtividadeReceita("Revenda ST", Anexo.I, D("23311.13"), com_st_ou_monofasico=True),
        AtividadeReceita("Serviço", Anexo.III, D("61478.63")),
    ]


def test_extrato_real_das_total_proximo_do_valor_real():
    resultado = calcular_das_multiplas_atividades(RBT12_EXTRATO, _atividades_extrato_real())
    das_real_extrato = D("14477.63")
    # O módulo ainda não exclui a parcela de ICMS já retida via ST/monofásico
    # da alíquota combinada do Anexo I (fica para etapa futura, quando o
    # parser identificar isso no extrato) — por isso o total calculado fica
    # acima do DAS real. Tolerância folgada o bastante para essa limitação
    # conhecida, mas apertada o bastante para pegar um bug de anexo trocado
    # (ex.: aplicar a alíquota do Anexo I a tudo dá 12.804,78 — diferença de
    # 1.672,85 do real, fora da tolerância).
    tolerancia = D("1200.00")
    assert abs(resultado.das_total - das_real_extrato) <= tolerancia


def test_atividade_unica_bate_com_multiplas_atividades():
    receita = D("100000.00")
    via_atalho = calcular_das_atividade_unica(RBT12_EXTRATO, receita, Anexo.I)
    via_multiplas = calcular_das_multiplas_atividades(
        RBT12_EXTRATO, [AtividadeReceita("x", Anexo.I, receita)]
    ).das_total
    assert via_atalho == via_multiplas


def test_atividades_em_anexos_diferentes_nunca_usam_mesma_aliquota():
    aliquota_i = calcular_aliquota_efetiva(RBT12_EXTRATO, Anexo.I)
    aliquota_iii = calcular_aliquota_efetiva(RBT12_EXTRATO, Anexo.III)
    assert aliquota_i != aliquota_iii

    resultado = calcular_das_multiplas_atividades(RBT12_EXTRATO, _atividades_extrato_real())
    proporcao_revenda = resultado.das_por_atividade["Revenda tributada"] / D("54392.65")
    proporcao_servico = resultado.das_por_atividade["Serviço"] / D("61478.63")
    assert proporcao_revenda != proporcao_servico


def test_das_por_atividade_tem_uma_chave_por_atividade():
    atividades = _atividades_extrato_real()
    resultado = calcular_das_multiplas_atividades(RBT12_EXTRATO, atividades)
    assert len(resultado.das_por_atividade) == len(atividades)
    assert set(resultado.das_por_atividade.keys()) == {a.nome for a in atividades}


def test_soma_das_por_atividade_igual_das_total():
    resultado = calcular_das_multiplas_atividades(RBT12_EXTRATO, _atividades_extrato_real())
    assert sum(resultado.das_por_atividade.values(), D("0.00")) == resultado.das_total


def test_lista_de_atividades_vazia_levanta_value_error():
    with pytest.raises(ValueError):
        calcular_das_multiplas_atividades(RBT12_EXTRATO, [])


def test_aliquota_efetiva_media_calculada_corretamente():
    atividades = _atividades_extrato_real()
    resultado = calcular_das_multiplas_atividades(RBT12_EXTRATO, atividades)
    soma_receitas = sum((a.receita_atividade for a in atividades), D("0.00"))
    esperado = (resultado.das_total / soma_receitas).quantize(D("0.0001"))
    assert resultado.aliquota_efetiva_media == esperado
