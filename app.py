import os
import sys
import tempfile
from datetime import date
from decimal import Decimal

import streamlit as st
from loguru import logger
from pydantic import ValidationError

# Remove handler padrão e reconfigura com arquivo rotativo
logger.remove()
logger.add(
    sys.stderr,
    level="WARNING",
    format="{time:HH:mm:ss} | {level} | {message}",
)
logger.add(
    "logs/analise_iva.log",
    level="DEBUG",
    rotation="10 MB",      # novo arquivo a cada 10MB
    retention="7 days",    # mantém logs de 7 dias
    compression="zip",     # comprime logs antigos
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}",
    encoding="utf-8",
)

st.set_page_config(
    page_title="Analisador IVA",
    page_icon="🧮",
    layout="wide",
)

from src.analise.config_lc214 import Regime, Setor
from src.analise.decisao import analisar
from src.analise.exportador_ppt import PPTX_DISPONIVEL, gerar_ppt
from src.analise.exportador_word import DOCX_DISPONIVEL, gerar_word
from src.analise.formulario import DadosCliente, to_contexto
from src.analise.graficos import (
    grafico_barra_comparativo,
    grafico_dentro_fora,
    grafico_evolucao_transicao,
    grafico_gauge_aliquota,
    grafico_pizza_atual,
    grafico_pizzas_comparativo,
)
from src.analise.formatters import fmt_moeda, fmt_percentual
from src.analise.narrativa import gerar_narrativa
from src.parser.normalizador import DadosNormalizados, normalizar_extrato
from src.parser.pgdas_parser import ExtratoPGDAS, PGDASParserError, parsear_pgdas
from src.simples.das_calculado import calcular_das_multiplas_atividades
from src.simples.dentro_fora import ALIQUOTA_ALERTA_MIGRACAO, calcular_dentro_fora_extrato

# ---------------------------------------------------------------------------
# Mapeamentos e constantes
# ---------------------------------------------------------------------------
MODOS = ["📊 Sistema Atual", "🧮 Analisador IVA", "📥 Extrato PGDAS-D", "📄 Relatório"]

REGIME_MAP = {
    "Simples Nacional": Regime.SIMPLES,
    "Lucro Presumido": Regime.PRESUMIDO,
    "Lucro Real": Regime.REAL,
}

SETOR_MAP = {
    "Padrão": Setor.PADRAO,
    "Educação": Setor.EDUCACAO,
    "Saúde": Setor.SAUDE,
    "Dispositivos Médicos": Setor.DISPOSITIVOS_MED,
    "Acessibilidade": Setor.ACESSIBILIDADE,
    "Medicamentos": Setor.MEDICAMENTOS,
    "Alimentos": Setor.ALIMENTOS,
    "Higiene Baixa Renda": Setor.HIGIENE_BAIXA_RENDA,
    "Agropecuário": Setor.AGROPECUARIO,
    "Cultural": Setor.CULTURAL,
    "Desportivo": Setor.DESPORTIVO,
    "Segurança Nacional": Setor.SEGURANCA_NAC,
}

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
]

ANOS = list(range(2026, 2034))

# PIS/COFINS individuais por regime — usados só no Modo 1 (calculadora simples).
# Não estão em config_lc214.py (que só guarda o total combinado 3,65%/9,25%).
PIS_COFINS_INDIVIDUAL = {
    Regime.SIMPLES: (0.65, 3.00),
    Regime.PRESUMIDO: (0.65, 3.00),
    Regime.REAL: (1.65, 7.60),
}

# Labels em português para as chaves internas de `cenario.detalhes`,
# usadas na Memória de cálculo. Cobre as chaves reais dos 3 regimes
# (src/analise/regimes/{simples,presumido,real}.py) + cenário B
# compartilhado (_cenario_b_regime_regular). carga_bruta/carga_liquida/
# credito_aproveitado são campos de CenarioUnico, não chaves de
# `.detalhes` — mantidos aqui só por completude, nunca aparecem nesta
# tabela hoje.
LABELS_PT = {
    "ibs_cbs_das":            "IBS/CBS no DAS (Simples)",
    "credito_entrada":        "Crédito de entrada",
    "ibs_cbs_bruto":          "IBS/CBS bruto (regime regular)",
    "credito_regime_normal":  "Crédito — fornecedores regime normal",
    "credito_simples":        "Crédito — fornecedores Simples",
    "pis_cofins":             "PIS/COFINS",
    "pis_cofins_bruto":       "PIS/COFINS",
    "credito_pis_cofins":     "Crédito PIS/COFINS",
    "icms":                   "ICMS",
    "iss":                    "ISS",
    "reducao_icms_iss_aplicada": "Redução ICMS/ISS aplicada",
    "carga_bruta":            "Carga bruta",
    "carga_liquida":          "Carga líquida",
    "credito_aproveitado":    "Crédito aproveitado",
}


def _delta_economia(delta_absoluto: Decimal, delta_percentual: Decimal):
    """(delta_texto, delta_color) para st.metric — economia = verde/seta
    para baixo, aumento = vermelho/seta para cima, zero = sem seta.

    A direção da seta do st.metric é decidida só pelo sinal do texto de
    delta (começa com "-" => seta para baixo), nunca por delta_color —
    por isso a economia (delta > 0) precisa de um texto com "-" à frente
    combinado com delta_color="inverse" para sair verde com seta para
    baixo. delta_color="off" sozinho não remove a seta em zero — só
    remove a seta de fato passar delta=None.
    """
    if delta_absoluto > 0:
        return f"-{fmt_percentual(abs(delta_percentual))}", "inverse"
    if delta_absoluto < 0:
        return fmt_percentual(abs(delta_percentual)), "inverse"
    return None, "off"


def _calcular_por_dentro_fora(faturamento: Decimal, aliquota: Decimal) -> dict:
    # Por fora — padrão LC 214
    ibs_cbs_fora = faturamento * aliquota
    base_fora = faturamento

    # Por dentro — IBS/CBS compõe a base
    ibs_cbs_dentro = faturamento * aliquota / (1 + aliquota)
    base_dentro = faturamento - ibs_cbs_dentro

    vantajoso = "fora" if ibs_cbs_fora <= ibs_cbs_dentro else "dentro"
    return {
        "fora": {"base": base_fora, "tributo": ibs_cbs_fora},
        "dentro": {"base": base_dentro, "tributo": ibs_cbs_dentro},
        "vantajoso": vantajoso,
    }


# ---------------------------------------------------------------------------
# CSS customizado
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Base */
    .stApp { background-color: #FFFFFF; color: #1A1A1A; }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #1A1A1A !important; }
    [data-testid="stSidebar"] label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] p { color: #FFFFFF !important; }
    [data-testid="stSidebar"] .stRadio label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] .stSlider label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #2E8B57 !important; }

    /* Inputs sidebar */
    [data-testid="stSidebar"] input {
        background-color: #2A2A2A !important;
        color: #FFFFFF !important;
        border: 1px solid #2E8B57 !important;
        border-radius: 4px !important;
    }
    [data-testid="stSidebar"] .stSelectbox > div > div {
        background-color: #2A2A2A !important;
        color: #FFFFFF !important;
        border: 1px solid #2E8B57 !important;
    }

    /* Botões */
    .stButton > button {
        background-color: #2E8B57 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        width: 100% !important;
        padding: 0.75rem !important;
        font-size: 1rem !important;
        transition: background-color 0.2s !important;
    }
    .stButton > button:hover { background-color: #236B43 !important; }

    /* Cards */
    .card-migrar {
        background-color: #2E8B57;
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 10px;
        text-align: center;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(46,139,87,0.3);
    }
    .card-manter {
        background-color: #1A1A1A;
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 10px;
        text-align: center;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .card-dentro {
        border: 2px solid #cccccc;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .card-dentro.vantajoso {
        border: 2px solid #2E8B57;
        background-color: #F0FFF4;
    }
    .card-fora {
        border: 2px solid #cccccc;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .card-fora.vantajoso {
        border: 2px solid #2E8B57;
        background-color: #F0FFF4;
    }

    /* Narrativa */
    .narrativa-box {
        border: 1.5px solid #2E8B57;
        border-radius: 8px;
        padding: 1.2rem 1.5rem;
        background-color: #F9F9F9;
        font-size: 0.95rem;
        line-height: 1.7;
        color: #1A1A1A;
    }

    /* Métricas */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: #666666 !important;
    }

    /* Título principal */
    .titulo-app {
        color: #2E8B57;
        font-size: 2.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .subtitulo-app {
        color: #666666;
        font-size: 1rem;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .instrucao-box {
        border: 1.5px solid #2E8B57;
        border-radius: 8px;
        padding: 1rem 1.5rem;
        color: #1A1A1A;
        background-color: #FFFFFF;
    }

    hr { border-color: #2E8B57 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar — seleção de modo + formulário
# ---------------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    st.markdown("## Analisador IVA")

    modo = st.radio("Modo", MODOS, index=1, key="modo_selecionado")

    # ------------------------------------------------------------------
    # MODO 1 — Sistema Atual
    # ------------------------------------------------------------------
    if modo == MODOS[0]:
        faturamento_atual = st.number_input(
            "Faturamento bruto (R$)", min_value=0.0, step=1000.0, format="%.2f"
        )
        regime_atual_label = st.selectbox("Regime", list(REGIME_MAP.keys()), key="regime_atual")
        setor_atual_label = st.selectbox("Setor", list(SETOR_MAP.keys()), key="setor_atual")
        uf_atual = st.selectbox("UF", UFS, key="uf_atual")
        ano_atual = st.selectbox("Ano de referência", ANOS, key="ano_atual")

        st.markdown("**Alíquotas declaradas**")
        pis_default, cofins_default = PIS_COFINS_INDIVIDUAL[REGIME_MAP[regime_atual_label]]
        pis_pct = st.number_input(
            "PIS (%)", min_value=0.0, value=pis_default, step=0.05, format="%.2f",
            key=f"pis_pct_{regime_atual_label}",
        )
        cofins_pct = st.number_input(
            "COFINS (%)", min_value=0.0, value=cofins_default, step=0.05, format="%.2f",
            key=f"cofins_pct_{regime_atual_label}",
        )
        icms_pct_atual = st.number_input("ICMS (%)", min_value=0.0, value=19.0, step=0.5, format="%.2f")
        iss_pct_atual = st.number_input("ISS (%)", min_value=0.0, value=5.0, step=0.5, format="%.2f")
        ipi_pct_atual = st.number_input("IPI (%)", min_value=0.0, value=0.0, step=0.5, format="%.2f")

        calcular_clicado = st.button("Calcular", key="btn_calcular_atual")

    # ------------------------------------------------------------------
    # MODO 2 — Analisador IVA
    # ------------------------------------------------------------------
    elif modo == MODOS[1]:
        faturamento = st.number_input(
            "Faturamento anual (R$)", min_value=0.0, step=1000.0, format="%.2f"
        )
        regime_label = st.selectbox("Regime atual", list(REGIME_MAP.keys()))
        setor_label = st.selectbox("Setor", list(SETOR_MAP.keys()))
        uf = st.selectbox("UF", UFS)
        ano = st.selectbox("Ano de referência", ANOS)

        st.markdown("**Perfil de operações**")
        percentual_b2b = st.slider("% vendas B2B", 0, 100, 50)

        st.markdown("**Compras**")
        compras_normal = st.number_input(
            "Fornecedores regime normal (R$)", min_value=0.0, step=1000.0, format="%.2f"
        )
        compras_simples = st.number_input(
            "Fornecedores Simples (R$)", min_value=0.0, step=1000.0, format="%.2f"
        )
        compras_isento = st.number_input(
            "Fornecedores isentos (R$)", min_value=0.0, step=1000.0, format="%.2f"
        )
        aliquota_das = st.number_input(
            "Alíquota IBS/CBS no DAS do fornecedor (%)",
            min_value=0.0, value=0.5, step=0.1, format="%.2f",
        )

        metodo_simples = None
        if REGIME_MAP[regime_label] == Regime.SIMPLES:
            st.divider()
            st.subheader("Simples: por dentro ou por fora?")
            metodo_simples = st.radio(
                "Cálculo IBS/CBS",
                ["Por dentro", "Por fora"],
                key="metodo_simples",
                help=(
                    "Por dentro: IBS/CBS compõe a própria base (como era o ICMS). "
                    "Por fora: IBS/CBS é adicionado sobre o preço — padrão LC 214."
                ),
            )

        with st.expander("Tributos atuais (opcional)"):
            icms_input = st.number_input(
                "ICMS efetivo (%)", min_value=0.0, value=None, step=0.1, format="%.2f",
                placeholder="deixe vazio para usar padrão 19%",
            )
            iss_input = st.number_input(
                "ISS efetivo (%)", min_value=0.0, value=None, step=0.1, format="%.2f",
                placeholder="deixe vazio para usar padrão 5%",
            )
            pis_cofins_input = st.number_input(
                "PIS+COFINS efetivo (%)", min_value=0.0, value=None, step=0.1, format="%.2f",
                placeholder="deixe vazio para usar padrão do regime",
            )

        analisar_clicado = st.button("Analisar", key="btn_analisar_iva")

    # ------------------------------------------------------------------
    # MODO 3 — Extrato PGDAS-D
    # ------------------------------------------------------------------
    elif modo == MODOS[2]:
        st.markdown("**Upload do extrato**")
        arquivo_pdf = st.file_uploader(
            "Extrato PGDAS-D (PDF)",
            type=["pdf"],
            key="upload_pgdas",
            help="Extrato gerado no portal do Simples Nacional (PGDAS-D).",
        )

        st.markdown("**Complemento — o operador informa:**")
        ano_pgdas = st.selectbox(
            "Ano de referência IBS/CBS", ANOS, index=1, key="ano_pgdas",
        )
        percentual_b2b_pgdas = st.slider("% vendas B2B", 0, 100, 50, key="b2b_pgdas")

        st.markdown("**Compras (para crédito de entrada)**")
        compras_normal_pgdas = st.number_input(
            "Fornecedores regime normal (R$)",
            min_value=0.0, step=1000.0, format="%.2f", key="comp_normal_pgdas",
        )
        compras_simples_pgdas = st.number_input(
            "Fornecedores Simples (R$)",
            min_value=0.0, step=1000.0, format="%.2f", key="comp_simples_pgdas",
        )
        compras_isento_pgdas = st.number_input(
            "Fornecedores isentos (R$)",
            min_value=0.0, step=1000.0, format="%.2f", key="comp_isento_pgdas",
        )

        setor_pgdas_label = st.selectbox(
            "Setor (para redução Art. 128)", list(SETOR_MAP.keys()), key="setor_pgdas",
        )

        processar_pgdas = st.button("Processar Extrato", key="btn_pgdas")

    # ------------------------------------------------------------------
    # MODO 4 — Relatório
    # ------------------------------------------------------------------
    elif modo == MODOS[3]:
        nome_cliente = ""
        data_relatorio = date.today()
        observacoes = ""
        gerar_word_clicado = False
        gerar_ppt_clicado = False

        if st.session_state.get("resultado") is None:
            st.warning("Execute uma análise primeiro.")
        else:
            nome_cliente = st.text_input("Nome do cliente")
            data_relatorio = st.date_input("Data do relatório", value=date.today())
            observacoes = st.text_area("Observações adicionais")

            if not DOCX_DISPONIVEL:
                st.caption("python-docx não instalado — exportação Word desabilitada.")
            gerar_word_clicado = st.button(
                "Gerar Word", key="btn_gerar_word", disabled=not DOCX_DISPONIVEL
            )

            if not PPTX_DISPONIVEL:
                st.caption("python-pptx não instalado — exportação PPT desabilitada.")
            gerar_ppt_clicado = st.button(
                "Gerar PPT", key="btn_gerar_ppt", disabled=not PPTX_DISPONIVEL
            )

# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
if modo == MODOS[0] and calcular_clicado:
    faturamento_D = Decimal(str(faturamento_atual))
    aliquotas = {
        "PIS": Decimal(str(pis_pct)),
        "COFINS": Decimal(str(cofins_pct)),
        "ICMS": Decimal(str(icms_pct_atual)),
        "ISS": Decimal(str(iss_pct_atual)),
        "IPI": Decimal(str(ipi_pct_atual)),
    }
    valores = {nome: (faturamento_D * aliquota / 100) for nome, aliquota in aliquotas.items()}
    total = sum(valores.values())
    aliquota_efetiva = (total / faturamento_D) if faturamento_D > 0 else Decimal("0")

    st.session_state["resultado_atual"] = {
        "faturamento": faturamento_D,
        "aliquotas": aliquotas,
        "valores": valores,
        "total": total,
        "aliquota_efetiva": aliquota_efetiva,
        "contexto": {
            "regime": regime_atual_label,
            "setor": setor_atual_label,
            "uf": uf_atual,
            "ano": ano_atual,
        },
    }

elif modo == MODOS[1] and analisar_clicado:
    try:
        kwargs = dict(
            faturamento_anual=Decimal(str(faturamento)),
            regime_atual=REGIME_MAP[regime_label],
            setor=SETOR_MAP[setor_label],
            uf=uf,
            ano_referencia=int(ano),
            percentual_b2b=Decimal(str(percentual_b2b / 100)),
            compras_fornecedor_regime_normal=Decimal(str(compras_normal)),
            compras_fornecedor_simples=Decimal(str(compras_simples)),
            compras_fornecedor_isento=Decimal(str(compras_isento)),
            aliquota_ibs_cbs_das_fornecedor=Decimal(str(aliquota_das / 100)),
        )
        if icms_input is not None:
            kwargs["icms_aliquota_efetiva"] = Decimal(str(icms_input / 100))
        if iss_input is not None:
            kwargs["iss_aliquota_efetiva"] = Decimal(str(iss_input / 100))
        if pis_cofins_input is not None:
            kwargs["pis_cofins_aliquota_efetiva"] = Decimal(str(pis_cofins_input / 100))

        dados = DadosCliente(**kwargs)
    except ValidationError as exc:
        erros = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
        st.session_state["erro"] = "Dados inválidos: " + " | ".join(erros)
        st.session_state["resultado"] = None
        logger.warning("Formulário inválido: {}", exc.errors())
    else:
        try:
            ctx = to_contexto(dados)
            resultado = analisar(ctx)
            st.session_state["resultado"] = resultado
            st.session_state["narrativa"] = gerar_narrativa(resultado)
            st.session_state["erro"] = None
        except ValueError as exc:
            st.session_state["erro"] = f"Erro de configuração: {exc}"
            st.session_state["resultado"] = None
            logger.warning("ValueError no motor: {}", exc)
        except Exception:
            logger.exception("Erro inesperado no motor de análise")
            st.session_state["erro"] = (
                "Erro interno inesperado. Verifique os dados e tente novamente."
            )
            st.session_state["resultado"] = None

elif modo == MODOS[2] and processar_pgdas:
    if arquivo_pdf is None:
        st.session_state["erro_pgdas"] = "Nenhum arquivo carregado."
    else:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(arquivo_pdf.read())
                tmp_path = tmp.name

            extrato: ExtratoPGDAS = parsear_pgdas(tmp_path)
            os.unlink(tmp_path)

            dados_norm: DadosNormalizados = normalizar_extrato(
                extrato=extrato,
                percentual_b2b=Decimal(str(percentual_b2b_pgdas / 100)),
                compras_regime_normal=Decimal(str(compras_normal_pgdas)),
                compras_simples=Decimal(str(compras_simples_pgdas)),
                compras_isento=Decimal(str(compras_isento_pgdas)),
                ano_referencia=int(ano_pgdas),
                setor=SETOR_MAP[setor_pgdas_label],
            )

            ctx = to_contexto(dados_norm.dados_cliente)
            resultado_pgdas = analisar(ctx)
            das_real = calcular_das_multiplas_atividades(extrato.rbt12, dados_norm.atividades)
            dentro_fora = calcular_dentro_fora_extrato(dados_norm, extrato.rbt12)

            st.session_state["extrato"] = extrato
            st.session_state["dados_norm"] = dados_norm
            st.session_state["resultado_pgdas"] = resultado_pgdas
            st.session_state["das_real"] = das_real
            st.session_state["dentro_fora"] = dentro_fora
            st.session_state["narrativa_pgdas"] = gerar_narrativa(resultado_pgdas)
            st.session_state["erro_pgdas"] = None
            st.session_state["resultado"] = resultado_pgdas  # alimenta o Modo Relatório

        except PGDASParserError as exc:
            logger.warning("Falha ao parsear PGDAS: {}", exc)
            st.session_state["erro_pgdas"] = f"Não foi possível ler o extrato: {exc}"
        except ValidationError as exc:
            erros = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
            st.session_state["erro_pgdas"] = "Dados inválidos: " + " | ".join(erros)
            logger.warning("ValidationError no Modo 3: {}", exc.errors())
        except Exception:
            logger.exception("Erro inesperado no Modo 3")
            st.session_state["erro_pgdas"] = "Erro interno inesperado."

elif modo == MODOS[3]:
    resultado_para_relatorio = st.session_state.get("resultado")
    if resultado_para_relatorio is not None:
        if gerar_word_clicado:
            try:
                st.session_state["docx_bytes"] = gerar_word(
                    resultado_para_relatorio, nome_cliente, data_relatorio, observacoes
                )
                st.session_state["erro_relatorio"] = None
            except RuntimeError as exc:
                st.session_state["erro_relatorio"] = str(exc)
                logger.warning("Falha ao gerar Word: {}", exc)
            except Exception:
                logger.exception("Erro inesperado ao gerar Word")
                st.session_state["erro_relatorio"] = (
                    "Erro interno ao gerar Word. Tente novamente."
                )
        if gerar_ppt_clicado:
            try:
                st.session_state["pptx_bytes"] = gerar_ppt(
                    resultado_para_relatorio, nome_cliente, data_relatorio
                )
                st.session_state["erro_relatorio"] = None
            except RuntimeError as exc:
                st.session_state["erro_relatorio"] = str(exc)
                logger.warning("Falha ao gerar PPT: {}", exc)
            except Exception:
                logger.exception("Erro inesperado ao gerar PPT")
                st.session_state["erro_relatorio"] = (
                    "Erro interno ao gerar PPT. Tente novamente."
                )

# ---------------------------------------------------------------------------
# Área principal
# ---------------------------------------------------------------------------
col_logo, col_titulo = st.columns([1, 4])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=80)
with col_titulo:
    st.markdown('<h1 class="titulo-app">Analisador IVA</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitulo-app">Simulação IBS/CBS — LC 214/2025</p>', unsafe_allow_html=True
    )

st.divider()

# ------------------------------------------------------------------
# MODO 1 — Área principal
# ------------------------------------------------------------------
if modo == MODOS[0]:
    ra = st.session_state.get("resultado_atual")
    if ra is None:
        st.markdown(
            '<div class="instrucao-box">Preencha os dados na barra lateral e clique em '
            "<strong>Calcular</strong>.</div>",
            unsafe_allow_html=True,
        )
    else:
        cols = st.columns(5)
        for col, nome in zip(cols, ["PIS", "COFINS", "ICMS", "ISS", "IPI"]):
            col.metric(nome, fmt_moeda(ra["valores"][nome]))

        st.write("")
        st.markdown(
            f'<div class="card-migrar">Total: {fmt_moeda(ra["total"])} '
            f'({fmt_percentual(ra["aliquota_efetiva"] * 100)} efetivo)</div>',
            unsafe_allow_html=True,
        )

        st.write("")
        st.plotly_chart(grafico_pizza_atual(ra["valores"]), use_container_width=True)

        with st.expander("Memória de cálculo", expanded=False):
            ctx_info = ra["contexto"]
            st.caption(
                f"Regime: {ctx_info['regime']} | Setor: {ctx_info['setor']} | "
                f"UF: {ctx_info['uf']} | Ano: {ctx_info['ano']}"
            )
            linhas = {
                nome: {
                    "Base de cálculo": fmt_moeda(ra["faturamento"]),
                    "Alíquota": fmt_percentual(ra["aliquotas"][nome]),
                    "Valor": fmt_moeda(valor),
                }
                for nome, valor in ra["valores"].items()
            }
            st.table(linhas)

# ------------------------------------------------------------------
# MODO 2 — Área principal
# ------------------------------------------------------------------
elif modo == MODOS[1]:
    erro = st.session_state.get("erro")
    resultado = st.session_state.get("resultado")

    if erro:
        st.error(f"Não foi possível concluir a análise: {erro}")
    elif resultado is None:
        st.markdown(
            '<div class="instrucao-box">Preencha os dados do cliente na barra lateral e '
            "clique em <strong>Analisar</strong>.<br>O resultado da simulação IBS/CBS "
            "aparecerá aqui.</div>",
            unsafe_allow_html=True,
        )
    else:
        narrativa = st.session_state.get("narrativa", "")
        cenario_a = resultado.cenarios.cenario_a
        cenario_b = resultado.cenarios.cenario_b

        # Bloco 1 — Métricas
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Carga Atual",
            fmt_moeda(cenario_a.carga_liquida),
            f"{fmt_percentual(cenario_a.aliquota_efetiva * 100)} efetivo",
            delta_color="off",
        )
        col2.metric(
            "Carga IVA Regular",
            fmt_moeda(cenario_b.carga_liquida),
            f"{fmt_percentual(cenario_b.aliquota_efetiva * 100)} efetivo",
            delta_color="off",
        )
        delta_texto, cor_delta = _delta_economia(resultado.delta_absoluto, resultado.delta_percentual)
        col3.metric(
            "Economia/Aumento",
            fmt_moeda(abs(resultado.delta_absoluto)),
            delta_texto,
            delta_color=cor_delta,
        )

        st.write("")

        # Bloco 2 — Recomendação
        if resultado.recomendacao == "MIGRAR_REGIME_REGULAR":
            st.markdown(
                '<div class="card-migrar">✓ Migrar para Regime Regular</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="card-manter">→ Manter Regime Atual</div>',
                unsafe_allow_html=True,
            )

        st.write("")

        # Bloco 3 — Pizzas comparativas + gauge de alíquota efetiva
        col_g1, col_g2 = st.columns([3, 2])
        with col_g1:
            st.plotly_chart(grafico_pizzas_comparativo(resultado), use_container_width=True)
        with col_g2:
            st.plotly_chart(grafico_gauge_aliquota(resultado), use_container_width=True)

        # Bloco 4 — Barra comparativa (largura total)
        st.plotly_chart(grafico_barra_comparativo(resultado), use_container_width=True)

        # Evolução da transição 2026-2033 — qualquer regime, não só Simples
        st.plotly_chart(grafico_evolucao_transicao(resultado.ctx), use_container_width=True)

        # Bloco 5 — Por dentro vs. Por fora (só Simples)
        if resultado.ctx.regime == Regime.SIMPLES:
            st.write("")
            st.subheader("Por dentro vs. Por fora")
            pdf = _calcular_por_dentro_fora(resultado.ctx.faturamento, resultado.ctx.ibs_cbs_total)
            col_dentro, col_fora = st.columns(2)
            classe_dentro = "card-dentro vantajoso" if pdf["vantajoso"] == "dentro" else "card-dentro"
            classe_fora = "card-fora vantajoso" if pdf["vantajoso"] == "fora" else "card-fora"
            with col_dentro:
                st.markdown(
                    f'<div class="{classe_dentro}"><strong>Por dentro</strong><br>'
                    f'IBS/CBS: {fmt_moeda(pdf["dentro"]["tributo"])}<br>'
                    f'Base: {fmt_moeda(pdf["dentro"]["base"])}</div>',
                    unsafe_allow_html=True,
                )
                st.caption("IBS_CBS = Preço × alíquota / (1 + alíquota)")
            with col_fora:
                st.markdown(
                    f'<div class="{classe_fora}"><strong>Por fora</strong><br>'
                    f'IBS/CBS: {fmt_moeda(pdf["fora"]["tributo"])}<br>'
                    f'Base: {fmt_moeda(pdf["fora"]["base"])}</div>',
                    unsafe_allow_html=True,
                )
                st.caption("IBS_CBS = Preço × alíquota")
            st.plotly_chart(grafico_dentro_fora(pdf), use_container_width=True)

        # Bloco 6 — Narrativa
        st.write("")
        st.markdown(f'<div class="narrativa-box">{narrativa}</div>', unsafe_allow_html=True)

        # Bloco 7 — Alertas
        if resultado.alertas:
            st.write("")
            for alerta in resultado.alertas:
                st.warning(alerta, icon="⚠️")

        # Bloco 8 — Memória de cálculo
        with st.expander("Memória de cálculo", expanded=False):
            st.markdown(f"**Cenário A — {cenario_a.nome}**")
            detalhes_a = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_a.detalhes.items() if isinstance(v, Decimal)
            }
            st.table(detalhes_a)

            st.markdown(f"**Cenário B — {cenario_b.nome}**")
            detalhes_b = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_b.detalhes.items() if isinstance(v, Decimal)
            }
            st.table(detalhes_b)

# ------------------------------------------------------------------
# MODO 3 — Extrato PGDAS-D — Área principal
# ------------------------------------------------------------------
elif modo == MODOS[2]:
    erro_pgdas = st.session_state.get("erro_pgdas")
    resultado_pgdas = st.session_state.get("resultado_pgdas")
    extrato = st.session_state.get("extrato")
    das_real = st.session_state.get("das_real")
    dentro_fora = st.session_state.get("dentro_fora")
    dados_norm = st.session_state.get("dados_norm")

    if erro_pgdas:
        st.error(erro_pgdas)
    elif resultado_pgdas is None:
        st.markdown(
            '<div class="instrucao-box">Carregue o extrato PGDAS-D na barra '
            "lateral e clique em <strong>Processar Extrato</strong>.</div>",
            unsafe_allow_html=True,
        )
    else:
        # Cabeçalho com dados do cliente extraídos automaticamente
        st.markdown(f"### {extrato.razao_social}")
        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        col_info1.metric("CNPJ", extrato.cnpj_basico)
        col_info2.metric("UF", extrato.uf)
        col_info3.metric("Período", extrato.periodo_apuracao)
        col_info4.metric("RBT12", fmt_moeda(extrato.rbt12))

        st.divider()

        # Bloco 1 — DAS Real (calculado pelo módulo simples)
        st.subheader("DAS Real por Atividade")
        cols_das = st.columns(len(das_real.atividades) + 1)
        for i, (nome, valor) in enumerate(das_real.das_por_atividade.items()):
            cols_das[i].metric(
                nome[:30] + "..." if len(nome) > 30 else nome,
                fmt_moeda(valor),
            )
        cols_das[-1].metric("DAS Total", fmt_moeda(das_real.das_total))

        st.divider()

        # Bloco 2 — Por dentro vs Por fora
        st.subheader("IBS/CBS: Por dentro vs Por fora")
        col_d, col_f = st.columns(2)

        classe_dentro = "card-migrar" if dentro_fora.vantajoso == "por_dentro" else "card-manter"
        classe_fora = "card-migrar" if dentro_fora.vantajoso == "por_fora" else "card-manter"

        with col_d:
            st.markdown(
                f'<div class="{classe_dentro}"><strong>Por dentro</strong><br>'
                f"Tributo: {fmt_moeda(dentro_fora.tributo_por_dentro)}<br>"
                f"Base: {fmt_moeda(dentro_fora.base_por_dentro)}</div>",
                unsafe_allow_html=True,
            )
            st.caption("IBS_CBS = Preço × alíquota / (1 + alíquota)")

        with col_f:
            st.markdown(
                f'<div class="{classe_fora}"><strong>Por fora</strong><br>'
                f"Tributo: {fmt_moeda(dentro_fora.tributo_por_fora)}<br>"
                f"Base: {fmt_moeda(dentro_fora.base_por_fora)}</div>",
                unsafe_allow_html=True,
            )
            st.caption("IBS_CBS = Preço × alíquota")

        st.metric("Economia anual estimada", fmt_moeda(dentro_fora.economia_anual_estimada))

        # grafico_dentro_fora espera "dentro"/"fora" literais, não
        # "por_dentro"/"por_fora" — traduzido aqui antes de montar o dict.
        vantajoso_grafico = {"por_dentro": "dentro", "por_fora": "fora"}.get(
            dentro_fora.vantajoso, "equivalente"
        )
        st.plotly_chart(
            grafico_dentro_fora(
                {
                    "dentro": {
                        "base": dentro_fora.base_por_dentro,
                        "tributo": dentro_fora.tributo_por_dentro,
                    },
                    "fora": {
                        "base": dentro_fora.base_por_fora,
                        "tributo": dentro_fora.tributo_por_fora,
                    },
                    "vantajoso": vantajoso_grafico,
                }
            ),
            use_container_width=True,
        )

        st.divider()

        # Bloco 3 — Comparativo IBS/CBS (reusa motor existente)
        st.subheader("Comparativo IBS/CBS vs Sistema Atual")
        cenario_a = resultado_pgdas.cenarios.cenario_a
        cenario_b = resultado_pgdas.cenarios.cenario_b

        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Carga Atual", fmt_moeda(cenario_a.carga_liquida),
            f"{fmt_percentual(cenario_a.aliquota_efetiva * 100)} efetivo",
            delta_color="off",
        )
        col2.metric(
            "Carga IVA Regular", fmt_moeda(cenario_b.carga_liquida),
            f"{fmt_percentual(cenario_b.aliquota_efetiva * 100)} efetivo",
            delta_color="off",
        )
        delta_texto_pgdas, cor_delta_pgdas = _delta_economia(
            resultado_pgdas.delta_absoluto, resultado_pgdas.delta_percentual
        )
        col3.metric(
            "Economia/Aumento",
            fmt_moeda(abs(resultado_pgdas.delta_absoluto)),
            delta_texto_pgdas,
            delta_color=cor_delta_pgdas,
        )

        # Card recomendação
        if resultado_pgdas.recomendacao == "MIGRAR_REGIME_REGULAR":
            st.markdown(
                '<div class="card-migrar">✓ Migrar para Regime Regular</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="card-manter">→ Manter Regime Atual</div>',
                unsafe_allow_html=True,
            )

        # Gráficos existentes reutilizados
        col_g1, col_g2 = st.columns([3, 2])
        with col_g1:
            st.plotly_chart(grafico_pizzas_comparativo(resultado_pgdas), use_container_width=True)
        with col_g2:
            st.plotly_chart(grafico_gauge_aliquota(resultado_pgdas), use_container_width=True)
        st.plotly_chart(grafico_barra_comparativo(resultado_pgdas), use_container_width=True)
        # resultado_pgdas.ctx (não uma variável "ctx" solta) — evita
        # NameError em reruns sem novo clique no botão de processar.
        st.plotly_chart(
            grafico_evolucao_transicao(resultado_pgdas.ctx), use_container_width=True
        )

        # Narrativa
        st.markdown(
            f'<div class="narrativa-box">{st.session_state.get("narrativa_pgdas", "")}</div>',
            unsafe_allow_html=True,
        )

        # Alertas — normalizador + motor
        alertas = dados_norm.alertas_normalizacao + resultado_pgdas.alertas
        for alerta in alertas:
            st.warning(alerta, icon="⚠️")

        # Observações por dentro vs por fora — reconstruídas a partir dos
        # campos Decimal de `dentro_fora` (fmt_moeda/fmt_percentual), não
        # de `dentro_fora.observacoes` (strings pré-formatadas sem passar
        # por fmt_moeda, com "|" como separador).
        with st.expander("Detalhes por dentro vs por fora", expanded=False):
            st.info(f"Tributo por fora: {fmt_moeda(dentro_fora.tributo_por_fora)}")
            st.info(f"Tributo por dentro: {fmt_moeda(dentro_fora.tributo_por_dentro)}")
            st.info(
                f"Diferença: {fmt_moeda(dentro_fora.diferenca_tributo)} "
                f"({fmt_percentual(dentro_fora.diferenca_percentual)})"
            )
            if dentro_fora.vantajoso == "por_fora":
                st.info(
                    f"Por fora é mais vantajoso: tributo menor em "
                    f"{fmt_moeda(dentro_fora.diferenca_tributo)} "
                    f"({fmt_percentual(dentro_fora.diferenca_percentual)})."
                )
            elif dentro_fora.vantajoso == "por_dentro":
                st.info(
                    f"Por dentro é mais vantajoso: tributo menor em "
                    f"{fmt_moeda(dentro_fora.diferenca_tributo)} "
                    f"({fmt_percentual(dentro_fora.diferenca_percentual)})."
                )
            else:
                st.info("Diferença inferior a R$ 0,01 — regimes equivalentes para esta alíquota.")
            st.info(
                f"Economia anual estimada: {fmt_moeda(dentro_fora.economia_anual_estimada)} "
                "(diferença × 12)."
            )
            if dentro_fora.aliquota_efetiva > ALIQUOTA_ALERTA_MIGRACAO:
                st.info(
                    "Alíquota efetiva acima de 15% — avaliar migração para regime regular IBS/CBS."
                )

        # Memória de cálculo
        with st.expander("Memória de cálculo", expanded=False):
            st.markdown(f"**Cenário A — {cenario_a.nome}**")
            detalhes_a = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_a.detalhes.items()
                if isinstance(v, Decimal)
            }
            st.table(detalhes_a)
            st.markdown(f"**Cenário B — {cenario_b.nome}**")
            detalhes_b = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_b.detalhes.items()
                if isinstance(v, Decimal)
            }
            st.table(detalhes_b)

# ------------------------------------------------------------------
# MODO 4 — Área principal
# ------------------------------------------------------------------
else:
    resultado_iva = st.session_state.get("resultado")
    if resultado_iva is None:
        st.markdown(
            '<div class="instrucao-box">Execute uma análise no modo '
            "<strong>Analisador IVA</strong> primeiro.</div>",
            unsafe_allow_html=True,
        )
    else:
        col_resumo_a, col_resumo_b = st.columns(2)
        with col_resumo_a:
            st.metric("Carga Atual", fmt_moeda(resultado_iva.cenarios.cenario_a.carga_liquida))
            st.metric("Carga IVA Regular", fmt_moeda(resultado_iva.cenarios.cenario_b.carga_liquida))
        with col_resumo_b:
            st.metric("Delta", fmt_moeda(resultado_iva.delta_absoluto))
            st.metric("Recomendação", resultado_iva.recomendacao.replace("_", " ").title())

        erro_relatorio = st.session_state.get("erro_relatorio")
        if erro_relatorio:
            st.error(f"Não foi possível gerar o relatório: {erro_relatorio}")

        docx_bytes = st.session_state.get("docx_bytes")
        pptx_bytes = st.session_state.get("pptx_bytes")

        cliente_slug = nome_cliente.strip().replace(" ", "_").lower() or "cliente"
        data_slug = str(data_relatorio).replace("-", "")

        if docx_bytes:
            st.download_button(
                "⬇️ Baixar Word (.docx)",
                data=docx_bytes,
                file_name=f"analise_iva_{cliente_slug}_{data_slug}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if pptx_bytes:
            st.download_button(
                "⬇️ Baixar PPT (.pptx)",
                data=pptx_bytes,
                file_name=f"analise_iva_{cliente_slug}_{data_slug}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

        if not docx_bytes and not pptx_bytes:
            st.markdown(
                '<div class="instrucao-box">📄 Word e PPT — clique em '
                "<strong>Gerar Word</strong> ou <strong>Gerar PPT</strong> na barra lateral."
                "</div>",
                unsafe_allow_html=True,
            )
