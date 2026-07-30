"""Testes de integração do formulário Streamlit até o motor de cálculo.

Usa `streamlit.testing.v1.AppTest` para simular preenchimento da
sidebar e clique nos botões, garantindo que os valores digitados
chegam corretos ao motor (`DadosCliente` -> `to_contexto` -> `analisar`).

Os índices dos widgets (`at.number_input[i]`, `at.selectbox[i]`, ...)
seguem a ordem de renderização da sidebar em `app.py` para o Modo
"🧮 Analisador IVA" (modo padrão, `index=1` no `st.radio`). Se a ordem
dos widgets nesse modo mudar, os índices usados aqui precisam ser
atualizados.
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
    at.radio[0].set_value("🧮 Analisador IVA")
    at.run()
    at.number_input[0].set_value(1_200_000.0)  # Faturamento anual
    at.selectbox[0].set_value("Simples Nacional")
    at.selectbox[1].set_value("Alimentos")
    at.selectbox[2].set_value("PE")
    at.selectbox[3].set_value(2027)
    at.slider[0].set_value(60)  # % vendas B2B
    at.number_input[1].set_value(400_000.0)  # Fornecedores regime normal
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
    at.radio[0].set_value("🧮 Analisador IVA")
    at.run()
    at.number_input[0].set_value(0.0)
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
    at.radio[0].set_value("🧮 Analisador IVA")
    at.run()
    at.number_input[0].set_value(1_000_000.0)
    at.selectbox[0].set_value("Lucro Presumido")
    at.selectbox[1].set_value("Padrão")
    at.selectbox[2].set_value("SP")
    at.selectbox[3].set_value(2029)
    at.slider[0].set_value(100)
    at.number_input[5].set_value(0.0)  # ICMS efetivo (%) declarado como 0
    at.button[0].click()
    at.run()
    assert not at.exception
    resultado = at.session_state["resultado"]
    assert resultado is not None
    # ICMS declarado como 0 precisa chegar como 0 ao motor — não pode
    # cair silenciosamente no padrão de 19% (bug corrigido no item 5).
    assert resultado.ctx.icms == Decimal("0.00")
    assert resultado.cenarios.cenario_a.detalhes["icms"] == Decimal("0.00")
