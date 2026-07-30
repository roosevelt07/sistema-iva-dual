"""Testes do módulo `regimes.simples`."""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.formulario import ContextoCalculo
from src.analise.regimes.simples import calcular


def _ctx(**overrides):
    base = dict(
        regime=Regime.SIMPLES,
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


def test_delta_positivo_com_credito_de_entrada():
    ctx = _ctx(compras_regime_normal=D("100000"))
    resultado = calcular(ctx)
    assert resultado.delta > D("0.00")


def test_delta_zero_sem_credito_relevante():
    # Bruto é idêntico nos dois cenários (cbs_efetiva+ibs_efetiva == ibs_cbs_total);
    # sem compras, credito_b também é zero, então delta não pode ser negativo nem positivo.
    ctx = _ctx(compras_regime_normal=D("0"), compras_simples=D("0"))
    resultado = calcular(ctx)
    assert resultado.delta == D("0.00")


def test_carga_liquida_nunca_negativa():
    ctx = _ctx(faturamento=D("1000"), compras_regime_normal=D("500000"))
    resultado = calcular(ctx)
    assert resultado.cenario_a.carga_liquida >= D("0.00")
    assert resultado.cenario_b.carga_liquida >= D("0.00")


def test_cenario_a_nunca_tem_credito():
    for compras in (D("0"), D("50000"), D("999999")):
        ctx = _ctx(compras_regime_normal=compras, compras_simples=compras)
        resultado = calcular(ctx)
        assert resultado.cenario_a.credito_aproveitado == D("0.00")
