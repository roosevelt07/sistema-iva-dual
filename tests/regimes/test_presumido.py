"""Testes do módulo `regimes.presumido`."""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.formulario import ContextoCalculo
from src.analise.regimes.presumido import calcular


def _ctx(**overrides):
    base = dict(
        regime=Regime.PRESUMIDO,
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
        pis_cofins=D("0.0365"),
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


def test_icms_reduzido_10_por_cento_em_2029():
    ctx = _ctx(ano=2029, reducao_icms_iss_ano=D("0.10"))
    resultado = calcular(ctx)
    assert resultado.cenario_a.detalhes["reducao_icms_iss_aplicada"] == D("0.10")
    assert resultado.cenario_a.detalhes["icms"] == (
        ctx.faturamento * ctx.icms * (D("1") - D("0.10"))
    ).quantize(D("0.01"))


def test_icms_intocado_em_2027():
    ctx = _ctx(ano=2027, fase="2027-2028", reducao_icms_iss_ano=D("0.00"))
    resultado = calcular(ctx)
    assert resultado.cenario_a.detalhes["reducao_icms_iss_aplicada"] == D("0.00")
    assert resultado.cenario_a.detalhes["icms"] == (ctx.faturamento * ctx.icms).quantize(D("0.01"))


def test_cenario_b_carga_liquida_nunca_negativa():
    ctx = _ctx(faturamento=D("1000"), compras_regime_normal=D("500000"))
    resultado = calcular(ctx)
    assert resultado.cenario_b.carga_liquida >= D("0.00")


def test_pis_cofins_usa_3_65_para_presumido():
    ctx = _ctx(pis_cofins=D("0.0365"))
    resultado = calcular(ctx)
    esperado = (ctx.faturamento * D("0.0365")).quantize(D("0.01"))
    assert resultado.cenario_a.detalhes["pis_cofins"] == esperado
