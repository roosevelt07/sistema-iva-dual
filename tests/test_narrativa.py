"""Testes de `narrativa`."""

from decimal import Decimal as D

from src.analise.config_lc214 import FluxoComercial, Regime, Setor
from src.analise.decisao import analisar
from src.analise.formulario import ContextoCalculo
from src.analise.narrativa import gerar_narrativa


def _ctx(regime, **overrides):
    pis_cofins_padrao = D("0.0925") if regime == Regime.REAL else D("0.0365")
    base = dict(
        regime=regime,
        setor=Setor.ALIMENTOS,
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


def test_saida_nao_vazia():
    texto = gerar_narrativa(analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000"))))
    assert len(texto) > 0


def test_contem_faturamento_formatado_em_reais():
    texto = gerar_narrativa(analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000"))))
    assert "R$" in texto


def test_contem_recomendacao():
    texto = gerar_narrativa(analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000"))))
    assert "Recomendação" in texto


def test_alerta_presente_quando_ha_alerta():
    resultado = analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000"), alerta_placeholder_senado=True))
    texto = gerar_narrativa(resultado)
    assert "Atenção" in texto


def test_sem_alerta_quando_nao_ha_alerta():
    resultado = analisar(
        _ctx(
            Regime.SIMPLES,
            fluxo=FluxoComercial.B2B,
            compras_regime_normal=D("100000"),
            alerta_limite_simples=False,
            alerta_placeholder_senado=False,
        )
    )
    assert resultado.alertas == []
    texto = gerar_narrativa(resultado)
    assert "Atenção" not in texto


def test_sem_marcacao_markdown():
    texto = gerar_narrativa(analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000"))))
    assert "**" not in texto
    assert "##" not in texto
    assert "- " not in texto


def test_delta_positivo_contem_economia():
    resultado = analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000")))
    assert resultado.delta_absoluto > D("0")
    texto = gerar_narrativa(resultado)
    assert "economia" in texto


def test_delta_negativo_contem_aumento():
    resultado = analisar(
        _ctx(
            Regime.PRESUMIDO,
            reducao_icms_iss_ano=D("1.00"),
            compras_regime_normal=D("0"),
            compras_simples=D("0"),
        )
    )
    assert resultado.delta_absoluto < D("0")
    texto = gerar_narrativa(resultado)
    assert "aumento" in texto


def test_delta_zero_contem_sem_variacao():
    resultado = analisar(
        _ctx(Regime.SIMPLES, compras_regime_normal=D("0"), compras_simples=D("0"))
    )
    assert resultado.delta_absoluto == D("0")
    texto = gerar_narrativa(resultado)
    assert "sem variação" in texto


def test_recomendacao_migrar_ou_manter_no_texto():
    resultado_migrar = analisar(_ctx(Regime.SIMPLES, compras_regime_normal=D("500000")))
    resultado_manter = analisar(
        _ctx(Regime.SIMPLES, compras_regime_normal=D("0"), compras_simples=D("0"))
    )
    assert "migrar" in gerar_narrativa(resultado_migrar)
    assert "manter" in gerar_narrativa(resultado_manter)
