"""Testes de `formulario`.

Valida a ramificação por regime e crédito de entrada em `ContextoCalculo`,
gerado exclusivamente via `to_contexto()`.
"""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.formulario import DadosCliente, to_contexto


def _dados(**overrides):
    base = dict(
        faturamento_anual=D("1000000"),
        regime_atual=Regime.PRESUMIDO,
        setor=Setor.PADRAO,
        uf="SP",
        ano_referencia=2029,
        percentual_b2b=D("0.50"),
        compras_fornecedor_regime_normal=D("100000"),
        compras_fornecedor_simples=D("10000"),
        compras_fornecedor_isento=D("5000"),
    )
    base.update(overrides)
    return DadosCliente(**base)


def test_simples_alimentos_2027_mistura_b2b():
    dados = _dados(
        regime_atual=Regime.SIMPLES,
        setor=Setor.ALIMENTOS,
        ano_referencia=2027,
        percentual_b2b=D("0.60"),
    )
    ctx = to_contexto(dados)
    assert ctx.fluxo == FluxoComercial.MISTO
    assert ctx.fase == "2027-2028"


def test_presumido_padrao_2029_b2b_total():
    dados = _dados(regime_atual=Regime.PRESUMIDO, setor=Setor.PADRAO, ano_referencia=2029, percentual_b2b=D("1.0"))
    ctx = to_contexto(dados)
    assert ctx.fluxo == FluxoComercial.B2B
    assert ctx.pis_cofins == D("0.0365")


def test_real_padrao_2029_pis_cofins_nao_cumulativo():
    dados = _dados(regime_atual=Regime.REAL, setor=Setor.PADRAO, ano_referencia=2029)
    ctx = to_contexto(dados)
    assert ctx.pis_cofins == D("0.0925")


def test_simples_acima_limite_gera_alerta_sem_bloquear():
    dados = _dados(regime_atual=Regime.SIMPLES, faturamento_anual=D("5000000"))
    ctx = to_contexto(dados)
    assert ctx.alerta_limite_simples is True


def test_uf_sempre_uppercase():
    dados = _dados(uf="pe")
    ctx = to_contexto(dados)
    assert ctx.uf == "PE"


def test_fluxo_comercial_extremos():
    ctx_b2b = to_contexto(_dados(percentual_b2b=D("1.0")))
    ctx_b2c = to_contexto(_dados(percentual_b2b=D("0.0")))
    assert ctx_b2b.fluxo == FluxoComercial.B2B
    assert ctx_b2c.fluxo == FluxoComercial.B2C


def test_compras_isento_nao_gera_credito():
    ctx_sem_isento = to_contexto(_dados(compras_fornecedor_isento=D("0")))
    ctx_com_isento = to_contexto(_dados(compras_fornecedor_isento=D("999999")))
    assert ctx_sem_isento.credito_entrada_total == ctx_com_isento.credito_entrada_total


def test_reducao_icms_iss_2026_intocado():
    ctx = to_contexto(_dados(ano_referencia=2026))
    assert ctx.reducao_icms_iss_ano == D("0.00")


def test_alerta_placeholder_senado():
    ctx_2026 = to_contexto(_dados(ano_referencia=2026))
    ctx_2027 = to_contexto(_dados(ano_referencia=2027))
    assert ctx_2026.alerta_placeholder_senado is False
    assert ctx_2027.alerta_placeholder_senado is True


def test_icms_padrao_default_e_declarado():
    ctx_default = to_contexto(_dados(icms_aliquota_efetiva=None))
    ctx_declarado = to_contexto(_dados(icms_aliquota_efetiva=D("0.22")))
    assert ctx_default.icms == D("0.19")
    assert ctx_declarado.icms == D("0.22")
