"""Testes de `decisao`.

Valida o roteamento por regime, a recomendação final e os alertas
gerados a partir de `ResultadoCenarios`/`ContextoCalculo` já prontos.
"""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.decisao import analisar
from src.analise.formulario import ContextoCalculo


def _ctx(regime, **overrides):
    pis_cofins_padrao = D("0.0925") if regime == Regime.REAL else D("0.0365")
    base = dict(
        regime=regime,
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
        pis_cofins=pis_cofins_padrao,
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


def test_regime_simples_ativa_modulo_simples():
    resultado = analisar(_ctx(Regime.SIMPLES))
    assert resultado.cenarios.regime == Regime.SIMPLES


def test_regime_presumido_ativa_modulo_presumido():
    resultado = analisar(_ctx(Regime.PRESUMIDO))
    assert resultado.cenarios.regime == Regime.PRESUMIDO


def test_regime_real_ativa_modulo_real():
    resultado = analisar(_ctx(Regime.REAL))
    assert resultado.cenarios.regime == Regime.REAL


def test_delta_positivo_recomenda_migrar():
    resultado = analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000")))
    assert resultado.cenarios.delta > D("0")
    assert resultado.recomendacao == "MIGRAR_REGIME_REGULAR"


def test_delta_zero_recomenda_manter():
    resultado = analisar(
        _ctx(Regime.SIMPLES, compras_regime_normal=D("0"), compras_simples=D("0"))
    )
    assert resultado.cenarios.delta == D("0")
    assert resultado.recomendacao == "MANTER_REGIME_ATUAL"


def test_alerta_placeholder_senado_presente():
    resultado = analisar(_ctx(Regime.PRESUMIDO, alerta_placeholder_senado=True))
    assert any("Resolução do Senado" in a for a in resultado.alertas)


def test_alerta_nao_materialidade_presente():
    resultado = analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("1000")))
    assert abs(resultado.cenarios.delta) < D("500")
    assert any("não é material" in a for a in resultado.alertas)


def test_alerta_b2b_presente_quando_misto_e_manter():
    resultado = analisar(
        _ctx(
            Regime.SIMPLES,
            fluxo=FluxoComercial.MISTO,
            compras_regime_normal=D("0"),
            compras_simples=D("0"),
        )
    )
    assert resultado.recomendacao == "MANTER_REGIME_ATUAL"
    assert any("vendas B2B" in a for a in resultado.alertas)


def test_delta_percentual_zero_quando_carga_liquida_a_zero():
    resultado = analisar(
        _ctx(
            Regime.PRESUMIDO,
            faturamento=D("0"),
            compras_regime_normal=D("0"),
            compras_simples=D("0"),
        )
    )
    assert resultado.cenarios.cenario_a.carga_liquida == D("0.00")
    assert resultado.delta_percentual == D("0")
