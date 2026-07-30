from decimal import Decimal as D
from src.analise.config_lc214 import Regime, Setor
from src.analise.formulario import DadosCliente, to_contexto
from src.analise.decisao import analisar
from src.analise.narrativa import gerar_narrativa

casos = [
    dict(
        label="Simples / Alimentos / 2027 / Misto",
        faturamento_anual=D("1200000"),
        regime_atual=Regime.SIMPLES,
        setor=Setor.ALIMENTOS,
        uf="PE", ano_referencia=2027,
        percentual_b2b=D("0.60"),
        compras_fornecedor_regime_normal=D("400000"),
        compras_fornecedor_simples=D("100000"),
        compras_fornecedor_isento=D("50000"),
    ),
    dict(
        label="Presumido / Padrão / 2029 / B2B puro",
        faturamento_anual=D("3500000"),
        regime_atual=Regime.PRESUMIDO,
        setor=Setor.PADRAO,
        uf="SP", ano_referencia=2029,
        percentual_b2b=D("1.00"),
        compras_fornecedor_regime_normal=D("1200000"),
        compras_fornecedor_simples=D("200000"),
        compras_fornecedor_isento=D("0"),
    ),
    dict(
        label="Real / Saúde / 2029 / B2C puro",
        faturamento_anual=D("8000000"),
        regime_atual=Regime.REAL,
        setor=Setor.SAUDE,
        uf="RJ", ano_referencia=2029,
        percentual_b2b=D("0.00"),
        compras_fornecedor_regime_normal=D("2000000"),
        compras_fornecedor_simples=D("500000"),
        compras_fornecedor_isento=D("100000"),
    ),
]

for c in casos:
    label = c.pop("label")
    dados = DadosCliente(**c)
    ctx = to_contexto(dados)
    resultado = analisar(ctx)
    narrativa = gerar_narrativa(resultado)
    print(f"\n{'='*60}")
    print(f"CASO: {label}")
    print(f"{'='*60}")
    print(narrativa)
    print(f"\nDelta: R$ {resultado.delta_absoluto:,.2f} ({resultado.delta_percentual:.2f}%)")
    print(f"Recomendação: {resultado.recomendacao}")
