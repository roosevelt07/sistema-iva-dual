"""Testes de `credito`.

Valida o cálculo de crédito de entrada e as observações geradas para o
operador, isolado de qualquer lógica de carga tributária.
"""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.credito import calcular_credito
from src.analise.formulario import ContextoCalculo


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
        compras_regime_normal=D("100000"),
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
        alerta_placeholder_senado=False,
    )
    base.update(overrides)
    return ContextoCalculo(**base)


def test_so_compras_regime_normal():
    ctx = _ctx(compras_regime_normal=D("100000"), compras_simples=D("0"), compras_isento=D("0"))
    resultado = calcular_credito(ctx)
    assert resultado.total == D("100000") * D("0.265")


def test_so_compras_simples():
    ctx = _ctx(
        compras_regime_normal=D("0"),
        compras_simples=D("50000"),
        compras_isento=D("0"),
        aliquota_das_fornecedor=D("0.06"),
    )
    resultado = calcular_credito(ctx)
    assert resultado.total == D("50000") * D("0.06")


def test_compras_isento_gera_observacao_sem_credito():
    ctx = _ctx(compras_isento=D("20000"))
    resultado = calcular_credito(ctx)
    assert resultado.credito_fornecedor_isento == D("0.00")
    assert any("Art. 49" in obs for obs in resultado.observacoes)


def test_mix_dos_tres_tipos_isento_nunca_entra():
    ctx = _ctx(
        compras_regime_normal=D("100000"),
        compras_simples=D("50000"),
        compras_isento=D("999999"),
        aliquota_das_fornecedor=D("0.06"),
    )
    resultado = calcular_credito(ctx)
    esperado = (D("100000") * D("0.265")).quantize(D("0.01")) + (D("50000") * D("0.06")).quantize(D("0.01"))
    assert resultado.total == esperado


def test_aliquota_das_padrao_gera_observacao_de_estimativa():
    ctx = _ctx(compras_simples=D("10000"), aliquota_das_fornecedor=D("0.005"))
    resultado = calcular_credito(ctx)
    assert any("estimativa padrão" in obs for obs in resultado.observacoes)


def test_fase_2027_2028_gera_observacao_placeholder_senado():
    ctx = _ctx(fase="2027-2028")
    resultado = calcular_credito(ctx)
    assert any("Resolução do Senado" in obs for obs in resultado.observacoes)


def test_proporcao_alta_gera_observacao_de_consistencia():
    ctx = _ctx(faturamento=D("1000"), compras_regime_normal=D("100000"), ibs_cbs_total=D("0.265"))
    resultado = calcular_credito(ctx)
    assert resultado.proporcao_sobre_faturamento > D("0.30")
    assert any("mais de 30%" in obs for obs in resultado.observacoes)


def test_faturamento_zero_sem_erro():
    ctx = _ctx(faturamento=D("0"), compras_regime_normal=D("10000"))
    resultado = calcular_credito(ctx)
    assert resultado.proporcao_sobre_faturamento == D("0.00")


def test_valores_arredondados_em_duas_casas():
    ctx = _ctx(
        compras_regime_normal=D("100000.555"),
        compras_simples=D("333.333"),
        aliquota_das_fornecedor=D("0.005"),
    )
    resultado = calcular_credito(ctx)
    for valor in (
        resultado.credito_fornecedor_normal,
        resultado.credito_fornecedor_simples,
        resultado.credito_fornecedor_isento,
        resultado.total,
        resultado.proporcao_sobre_faturamento,
    ):
        assert valor.as_tuple().exponent >= -2
