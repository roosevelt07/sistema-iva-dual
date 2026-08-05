import base64
import os
import re
import sys
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import streamlit as st
from loguru import logger
from pydantic import ValidationError

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

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
MODOS = ["🧮 Analisador IVA"]

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


# `st.number_input` com type="number" HTML5 rejeita vírgula digitada —
# um operador BR digitando "602.000,90" tem a vírgula descartada pelo
# navegador, e o valor capturado colapsa para algo como "602,00". Por
# isso os campos monetários usam st.text_input + este parser estrito,
# em vez de number_input.
RE_MOEDA_BR = re.compile(r"^(\d+|\d{1,3}(\.\d{3})+)(,\d{1,2})?$")


def _parse_moeda_br(texto: str):
    """Retorna (valor, None) se válido, ou (None, mensagem_erro)."""
    texto = texto.strip()
    if not texto:
        return Decimal("0.00"), None
    if not RE_MOEDA_BR.match(texto):
        return None, f"Formato inválido: use 602.000,90 ou 602000,90 (não {texto!r})"
    limpo = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo), None
    except InvalidOperation:
        return None, f"Não foi possível interpretar: {texto!r}"


def _campo_moeda(label: str, key: str):
    texto = st.text_input(
        label, key=key, placeholder="0,00",
        help="Formato brasileiro: milhar com ponto, decimal com vírgula. Ex.: 602.000,90",
    )
    valor, erro = _parse_moeda_br(texto)
    if erro:
        st.caption(f"⚠️ {erro}")
    elif valor is not None:
        st.caption(f"✓ {fmt_moeda(valor)}")
    return valor


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
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

    :root {
      --teal-principal: #00B2A9;
      --teal-escuro: #007F78;
      --escuro: #2C2C2C;
      --cinza: #6B7280;
      --fundo-app: #FAFAF9;
      --fundo-card: #FFFFFF;
      --fonte-display: 'Space Grotesk', sans-serif;
      --fonte-corpo: 'Inter', sans-serif;
      --fonte-numerica: 'IBM Plex Mono', monospace;
    }

    /* Base */
    .stApp { background-color: var(--fundo-app); color: var(--escuro); font-family: var(--fonte-corpo); }

    /* Sidebar */
    [data-testid="stSidebar"] { background: linear-gradient(180deg, var(--escuro) 0%, #1F1F1F 100%) !important; }
    [data-testid="stSidebar"] label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] p { color: #FFFFFF !important; }
    [data-testid="stSidebar"] .stRadio label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] .stSlider label { color: #FFFFFF !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: var(--teal-principal) !important; font-family: var(--fonte-display); }

    /* Inputs sidebar */
    [data-testid="stSidebar"] input {
        background-color: #2A2A2A !important;
        color: #FFFFFF !important;
        border: 1px solid var(--teal-principal) !important;
        border-radius: 4px !important;
    }
    [data-testid="stSidebar"] .stSelectbox > div > div {
        background-color: #2A2A2A !important;
        color: #FFFFFF !important;
        border: 1px solid var(--teal-principal) !important;
    }

    /* Botões */
    .stButton > button {
        background-color: var(--teal-principal) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        width: 100% !important;
        padding: 0.75rem !important;
        font-size: 1rem !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 2px 8px rgba(0,178,169,0.25) !important;
        transition: background-color 0.2s !important;
    }
    .stButton > button:hover { background-color: var(--teal-escuro) !important; }

    /* Cards */
    .card-migrar {
        background-color: var(--teal-principal);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        text-align: center;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 1rem 0;
        font-family: var(--fonte-display);
        box-shadow: 0 8px 24px rgba(0,178,169,0.18);
        transition: transform 0.15s;
    }
    .card-migrar:hover { transform: translateY(-2px); }
    .card-manter {
        background-color: var(--escuro);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        text-align: center;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 1rem 0;
        font-family: var(--fonte-display);
        box-shadow: 0 8px 24px rgba(0,178,169,0.18);
        transition: transform 0.15s;
    }
    .card-manter:hover { transform: translateY(-2px); }
    .card-dentro {
        border: 2px solid #cccccc;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .card-dentro.vantajoso {
        border: 2px solid var(--teal-principal);
        background-color: rgba(0,178,169,0.06);
        box-shadow: 0 2px 8px rgba(0,178,169,0.12);
    }
    .card-fora {
        border: 2px solid #cccccc;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .card-fora.vantajoso {
        border: 2px solid var(--teal-principal);
        background-color: rgba(0,178,169,0.06);
        box-shadow: 0 2px 8px rgba(0,178,169,0.12);
    }

    /* Narrativa */
    .narrativa-box {
        border-left: 4px solid var(--teal-principal);
        border-radius: 0 8px 8px 0;
        padding: 1.2rem 1.5rem;
        background-color: #F9F9F9;
        font-size: 0.95rem;
        line-height: 1.7;
        color: var(--escuro);
    }

    /* Métricas */
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        font-family: var(--fonte-numerica);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        color: var(--cinza) !important;
    }

    /* Título principal */
    .titulo-app {
        color: var(--teal-principal);
        font-size: 2.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0.2rem;
        font-family: var(--fonte-display);
    }
    .subtitulo-app {
        color: var(--cinza);
        font-size: 1rem;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .instrucao-box {
        border: 1.5px solid var(--teal-principal);
        border-radius: 8px;
        padding: 1rem 1.5rem;
        color: var(--escuro);
        background-color: #FFFFFF;
    }

    hr { border-color: var(--teal-principal) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar — fonte dos dados + formulário
# ---------------------------------------------------------------------------
analisar_clicado = False
processar_pgdas = False

with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
    st.markdown("## Analisador IVA")

    tipo_entrada = st.radio(
        "Fonte dos dados",
        ["Entrada manual", "Upload PGDAS-D"],
        horizontal=True,
        key="tipo_entrada",
    )

    # ------------------------------------------------------------------
    # Entrada manual
    # ------------------------------------------------------------------
    if tipo_entrada == "Entrada manual":
        faturamento = _campo_moeda("Faturamento anual (R$)", key="faturamento_texto")
        regime_label = st.selectbox("Regime atual", list(REGIME_MAP.keys()))
        setor_label = st.selectbox("Setor", list(SETOR_MAP.keys()))
        uf = st.selectbox("UF", UFS)
        ano = st.selectbox("Ano de referência", ANOS)

        st.markdown("**Perfil de operações**")
        percentual_b2b = st.slider("% vendas B2B", 0, 100, 50)

        st.markdown("**Compras**")
        compras_normal = _campo_moeda("Fornecedores regime normal (R$)", key="compras_normal_texto")
        compras_simples = _campo_moeda("Fornecedores Simples (R$)", key="compras_simples_texto")
        compras_isento = _campo_moeda("Fornecedores isentos (R$)", key="compras_isento_texto")
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
    # Upload PGDAS-D
    # ------------------------------------------------------------------
    else:
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
        compras_normal_pgdas = _campo_moeda("Fornecedores regime normal (R$)", key="comp_normal_pgdas")
        compras_simples_pgdas = _campo_moeda("Fornecedores Simples (R$)", key="comp_simples_pgdas")
        compras_isento_pgdas = _campo_moeda("Fornecedores isentos (R$)", key="comp_isento_pgdas")

        setor_pgdas_label = st.selectbox(
            "Setor (para redução Art. 128)", list(SETOR_MAP.keys()), key="setor_pgdas",
        )

        processar_pgdas = st.button("Processar Extrato", key="btn_pgdas")

# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
if tipo_entrada == "Entrada manual" and analisar_clicado:
    st.session_state["fonte_resultado"] = "manual"
    if None in (faturamento, compras_normal, compras_simples, compras_isento):
        st.session_state["erro"] = (
            "Corrija os campos monetários com formato inválido antes de analisar."
        )
        st.session_state["resultado"] = None
    else:
        try:
            kwargs = dict(
                faturamento_anual=faturamento,
                regime_atual=REGIME_MAP[regime_label],
                setor=SETOR_MAP[setor_label],
                uf=uf,
                ano_referencia=int(ano),
                percentual_b2b=Decimal(str(percentual_b2b / 100)),
                compras_fornecedor_regime_normal=compras_normal,
                compras_fornecedor_simples=compras_simples,
                compras_fornecedor_isento=compras_isento,
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

elif tipo_entrada == "Upload PGDAS-D" and processar_pgdas:
    st.session_state["fonte_resultado"] = "pgdas"
    if arquivo_pdf is None:
        st.session_state["erro_pgdas"] = "Nenhum arquivo carregado."
    elif None in (compras_normal_pgdas, compras_simples_pgdas, compras_isento_pgdas):
        st.session_state["erro_pgdas"] = (
            "Corrija os campos monetários com formato inválido antes de processar."
        )
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
                compras_regime_normal=compras_normal_pgdas,
                compras_simples=compras_simples_pgdas,
                compras_isento=compras_isento_pgdas,
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
            st.session_state["resultado"] = resultado_pgdas  # alimenta a exportação inline

        except PGDASParserError as exc:
            logger.warning("Falha ao parsear PGDAS: {}", exc)
            st.session_state["erro_pgdas"] = f"Não foi possível ler o extrato: {exc}"
        except ValidationError as exc:
            erros = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
            st.session_state["erro_pgdas"] = "Dados inválidos: " + " | ".join(erros)
            logger.warning("ValidationError no fluxo PGDAS-D: {}", exc.errors())
        except Exception:
            logger.exception("Erro inesperado no fluxo PGDAS-D")
            st.session_state["erro_pgdas"] = "Erro interno inesperado."

# ---------------------------------------------------------------------------
# Área principal
# ---------------------------------------------------------------------------
if LOGO_PATH.exists():
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    st.markdown(
        f"""
        <div style="text-align:center; margin-bottom:0.5rem;">
            <img src="data:image/png;base64,{logo_b64}" width="80"
                 style="display:inline-block; margin-bottom:0.5rem;">
            <h1 class="titulo-app" style="margin:0;">Analisador IVA</h1>
            <p class="subtitulo-app" style="margin:0;">Simulação IBS/CBS — LC 214/2025</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown('<h1 class="titulo-app">Analisador IVA</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitulo-app">Simulação IBS/CBS — LC 214/2025</p>',
        unsafe_allow_html=True,
    )

st.divider()

fonte = st.session_state.get("fonte_resultado")

# ------------------------------------------------------------------
# Fluxo manual — Área principal
# ------------------------------------------------------------------
if fonte == "manual":
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
            st.table({"Valor": detalhes_a})

            st.markdown(f"**Cenário B — {cenario_b.nome}**")
            detalhes_b = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_b.detalhes.items() if isinstance(v, Decimal)
            }
            st.table({"Valor": detalhes_b})

# ------------------------------------------------------------------
# Fluxo PGDAS-D — Área principal
# ------------------------------------------------------------------
elif fonte == "pgdas":
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
            st.table({"Valor": detalhes_a})
            st.markdown(f"**Cenário B — {cenario_b.nome}**")
            detalhes_b = {
                LABELS_PT.get(k, k.replace("_", " ").title()): fmt_moeda(v)
                for k, v in cenario_b.detalhes.items()
                if isinstance(v, Decimal)
            }
            st.table({"Valor": detalhes_b})

# ------------------------------------------------------------------
# Instrução inicial — nada analisado ainda nesta sessão
# ------------------------------------------------------------------
else:
    if tipo_entrada == "Entrada manual":
        st.markdown(
            '<div class="instrucao-box">Preencha os dados do cliente na barra lateral e '
            "clique em <strong>Analisar</strong>.<br>O resultado da simulação IBS/CBS "
            "aparecerá aqui.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="instrucao-box">Carregue o extrato PGDAS-D na barra '
            "lateral e clique em <strong>Processar Extrato</strong>.</div>",
            unsafe_allow_html=True,
        )

# ------------------------------------------------------------------
# Exportação inline — comum aos dois fluxos, roda sempre que houver
# um resultado disponível em st.session_state["resultado"]
# ------------------------------------------------------------------
resultado_export = st.session_state.get("resultado")
if resultado_export is not None:
    st.divider()
    st.subheader("Exportar relatório")
    col_exp1, col_exp2, col_exp3 = st.columns([2, 1, 1])
    with col_exp1:
        nome_cliente = st.text_input("Nome do cliente", key="nome_cliente_export")
    with col_exp2:
        data_relatorio = st.date_input("Data", value=date.today(), key="data_export")
    with col_exp3:
        observacoes = st.text_area("Observações", key="obs_export", height=68)

    cliente_slug = nome_cliente.strip().replace(" ", "_").lower() or "cliente"
    data_slug = str(data_relatorio).replace("-", "")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if not DOCX_DISPONIVEL:
            st.caption("python-docx não instalado — exportação Word desabilitada.")
        if st.button("Gerar Word", disabled=not DOCX_DISPONIVEL, key="btn_word_inline"):
            try:
                st.session_state["docx_bytes"] = gerar_word(
                    resultado_export, nome_cliente, data_relatorio, observacoes,
                    dados_norm=st.session_state.get("dados_norm"),
                    extrato=st.session_state.get("extrato"),
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
        docx_bytes = st.session_state.get("docx_bytes")
        if docx_bytes:
            st.download_button(
                "⬇️ Baixar Word (.docx)",
                data=docx_bytes,
                file_name=f"analise_iva_{cliente_slug}_{data_slug}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_word_inline",
            )
    with col_btn2:
        if not PPTX_DISPONIVEL:
            st.caption("python-pptx não instalado — exportação PPT desabilitada.")
        if st.button("Gerar PPT", disabled=not PPTX_DISPONIVEL, key="btn_ppt_inline"):
            try:
                st.session_state["pptx_bytes"] = gerar_ppt(
                    resultado_export, nome_cliente, data_relatorio,
                    dados_norm=st.session_state.get("dados_norm"),
                    extrato=st.session_state.get("extrato"),
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
        pptx_bytes = st.session_state.get("pptx_bytes")
        if pptx_bytes:
            st.download_button(
                "⬇️ Baixar PPT (.pptx)",
                data=pptx_bytes,
                file_name=f"analise_iva_{cliente_slug}_{data_slug}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key="download_ppt_inline",
            )

    erro_relatorio = st.session_state.get("erro_relatorio")
    if erro_relatorio:
        st.error(f"Não foi possível gerar o relatório: {erro_relatorio}")
