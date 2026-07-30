"""Testes do módulo `regimes.real`."""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.formulario import ContextoCalculo
from src.analise.regimes.real import calcular


def _ctx(**overrides):
    base = dict(
        regime=Regime.REAL,
        setor=Setor.PADRAO,
        uf="SP",
        ano=2029,
        faturamento=D("1000000"),
        cbs_efetiva=D("0.088"),
        ibs_efetiva=D("0.177"),
        ibs_cbs_total=D("0.265"),
        fase="2029+",
        percentual_b2b=D("0.50"),
        percentual_b2c=D("0.50"),
        fluxo=FluxoComercial.MISTO,
        compras_regime_normal=D("0"),
        compras_simples=D("0"),
        compras_isento=D("0"),
        aliquota_das_fornecedor=D("0.005"),
        pis_cofins=D("0.0925"),
        icms=D("0.19"),
        iss=D("0.05"),
        reducao_icms_iss_ano=D("0.10"),
        credito_entrada_regime_normal=D("0.00"),
        credito_entrada_simples=D("0.00"),
        credito_entrada_total=D("0.00"),
        alerta_limite_simples=False,
        alerta_placeholder_senado=True,
    )
    base.update(overrides)
    return ContextoCalculo(**base)


def test_pis_cofins_usa_9_25_para_real():
    ctx = _ctx(pis_cofins=D("0.0925"))
    resultado = calcular(ctx)
    esperado = (ctx.faturamento * D("0.0925")).quantize(D("0.01"))
    assert resultado.cenario_a.detalhes["pis_cofins_bruto"] == esperado


def test_credito_pis_cofins_e_total_compras_vezes_9_25():
    ctx = _ctx(
        compras_regime_normal=D("50000"),
        compras_simples=D("20000"),
        compras_isento=D("5000"),
    )
    resultado = calcular(ctx)
    total_compras = D("50000") + D("20000") + D("5000")
    esperado = (total_compras * D("0.0925")).quantize(D("0.01"))
    assert resultado.cenario_a.detalhes["credito_pis_cofins"] == esperado


def test_cenario_b_carga_liquida_nunca_negativa():
    ctx = _ctx(faturamento=D("1000"), compras_regime_normal=D("500000"))
    resultado = calcular(ctx)
    assert resultado.cenario_b.carga_liquida >= D("0.00")


def test_credito_financeiro_ibs_cbs_maior_que_credito_fisico_pis_cofins():
    ctx = _ctx(compras_regime_normal=D("100000"), compras_simples=D("0"), compras_isento=D("0"))
    resultado = calcular(ctx)
    assert resultado.cenario_b.credito_aproveitado > resultado.cenario_a.credito_aproveitado
