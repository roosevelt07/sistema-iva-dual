"""Testes de integração do formulário Streamlit até o motor de cálculo.

Usa `streamlit.testing.v1.AppTest` para simular preenchimento da
sidebar e clique nos botões, garantindo que os valores digitados
chegam corretos ao motor (`DadosCliente` -> `to_contexto` -> `analisar`).

Os índices dos widgets (`at.number_input[i]`, `at.text_input[i]`,
`at.selectbox[i]`, ...) seguem a ordem de renderização da sidebar em
`app.py` para o fluxo "Entrada manual" (opção padrão do toggle "Fonte
dos dados", `at.radio[0]`). Os 4 campos monetários (faturamento +
3 de compras) são `st.text_input` com formato brasileiro
("602.000,90"), não `st.number_input` — ver `_parse_moeda_br`/
`_campo_moeda` em `app.py`. Se a ordem dos widgets desse fluxo mudar,
os índices usados aqui precisam ser atualizados.
"""

import os

os.environ["PYTHONPATH"] = "."

from decimal import Decimal

from streamlit.testing.v1 import AppTest


def _app():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    return at


def test_carregamento_inicial():
    at = _app()
    assert not at.exception


def test_simples_alimentos_2027():
    at = _app()
    at.radio[0].set_value("Entrada manual")
    at.run()
    at.text_input[0].set_value("1.200.000,00")  # Faturamento anual
    at.selectbox[0].set_value("Simples Nacional")
    at.selectbox[1].set_value("Alimentos")
    at.selectbox[2].set_value("PE")
    at.selectbox[3].set_value(2027)
    at.slider[0].set_value(60)  # % vendas B2B
    at.text_input[1].set_value("400.000,00")  # Fornecedores regime normal
    at.button[0].click()
    at.run()
    assert not at.exception
    resultado = at.session_state["resultado"]
    assert resultado is not None
    # Delta calculado pelo motor para este cenário (faturamento 1.2M,
    # Simples/Alimentos/PE/2027, 60% B2B, R$ 400k de compras regime normal,
    # demais campos no padrão): R$ 14.080,00.
    assert resultado.delta_absoluto == Decimal("14080.00")


def test_faturamento_zero_nao_quebra():
    at = _app()
    at.radio[0].set_value("Entrada manual")
    at.run()
    at.text_input[0].set_value("0,00")
    at.button[0].click()
    at.run()
    assert not at.exception
    # Deve mostrar erro de validação, não stack trace
    erro = at.session_state["erro"]
    assert erro is not None
    assert "inválidos" in erro.lower() or "maior" in erro.lower()
    assert at.session_state["resultado"] is None


def test_icms_zero_declarado_nao_usa_padrao():
    at = _app()
    at.radio[0].set_value("Entrada manual")
    at.run()
    at.text_input[0].set_value("1.000.000,00")
    at.selectbox[0].set_value("Lucro Presumido")
    at.selectbox[1].set_value("Padrão")
    at.selectbox[2].set_value("SP")
    at.selectbox[3].set_value(2029)
    at.slider[0].set_value(100)
    at.number_input[1].set_value(0.0)  # ICMS efetivo (%) declarado como 0
    at.button[0].click()
    at.run()
    assert not at.exception
    resultado = at.session_state["resultado"]
    assert resultado is not None
    # ICMS declarado como 0 precisa chegar como 0 ao motor — não pode
    # cair silenciosamente no padrão de 19% (bug corrigido no item 5).
    assert resultado.ctx.icms == Decimal("0.00")
    assert resultado.cenarios.cenario_a.detalhes["icms"] == Decimal("0.00")


def test_compras_com_centavos_formato_br_nao_e_truncado():
    """Regressão: valores monetários com centavos no formato brasileiro
    ("602.000,90") precisam chegar ao motor exatamente como digitados —
    não truncados/reduzidos por ambiguidade de separador de milhar."""
    at = _app()
    at.radio[0].set_value("Entrada manual")
    at.run()
    at.text_input[0].set_value("1.502.383,95")  # Faturamento anual
    at.selectbox[0].set_value("Lucro Real")
    at.selectbox[1].set_value("Padrão")
    at.selectbox[2].set_value("SP")
    at.selectbox[3].set_value(2029)
    at.text_input[1].set_value("602.000,90")  # Fornecedores regime normal
    at.button[0].click()
    at.run()
    assert not at.exception
    resultado = at.session_state["resultado"]
    assert resultado is not None
    assert resultado.ctx.compras_regime_normal == Decimal("602000.90")
