"""Parser de Extrato do Simples Nacional (PGDAS-D) em PDF.

Extrai texto via `pdftotext -layout` (subprocess — nunca pypdf, que perde
a formatação tabular do extrato) e estrutura os dados em `ExtratoPGDAS`.
Este módulo não calcula nada, só lê e estrutura.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import List, Optional

D = Decimal


class PGDASParserError(Exception):
    """Erro ao interpretar a estrutura do extrato PGDAS-D."""


@dataclass(frozen=True)
class BlocoAtividade:
    descricao: str
    receita_bruta_informada: Decimal
    irpj: Decimal
    csll: Decimal
    cofins: Decimal
    pis: Decimal
    inss_cpp: Decimal
    icms: Decimal
    ipi: Decimal
    iss: Decimal
    total: Decimal
    com_substituicao_tributaria: bool
    com_tributacao_monofasica: bool
    tributos_st: List[str]
    tributos_monofasicos: List[str]


@dataclass(frozen=True)
class ExtratoPGDAS:
    cnpj_basico: str
    razao_social: str
    municipio: str
    uf: str
    periodo_apuracao: str
    rpa: Decimal
    rbt12: Decimal
    fator_r: Optional[Decimal]
    sublimite_receita_anual: Decimal
    blocos_atividade: List[BlocoAtividade]
    das_total: Decimal
    das_irpj: Decimal
    das_csll: Decimal
    das_cofins: Decimal
    das_pis: Decimal
    das_inss_cpp: Decimal
    das_icms: Decimal
    das_ipi: Decimal
    das_iss: Decimal


# ---------------------------------------------------------------------------
# Regex — cabeçalho / apuração
# ---------------------------------------------------------------------------
RE_CNPJ = re.compile(r"CNPJ Básico:\s*([\d.]+)")
# `$` sem re.MULTILINE só marca o fim da string inteira, não fim de linha —
# sem essa flag a regex nunca fechava na linha real do extrato (sem
# `\s{2,}` antes da quebra de linha).
RE_RAZAO = re.compile(r"Nome Empresarial:\s*(.+?)(?:\s{2,}|$)", re.MULTILINE)
RE_MUNICIPIO = re.compile(r"Município:\s*(\S+)")
RE_UF = re.compile(r"\bUF:\s*([A-Z]{2})")
RE_PA = re.compile(r"Período de Apuração \(PA\):\s*(\d{2}/\d{4})")
RE_RPA = re.compile(r"Receita Bruta do PA.*?Competência\s+[\d.,]+\s+[\d.,]+\s+([\d.,]+)")
# No PDF real os números vêm ANTES do rótulo "(RBT12)", que aparece isolado
# na linha seguinte (o rótulo completo quebra em duas linhas no layout do
# extrato) — não depois, como a redação do enunciado sugeria.
RE_RBT12 = re.compile(
    r"Receita bruta acumulada nos doze meses anteriores ao PA\s+"
    r"[\d.,]+\s+[\d.,]+\s+([\d.,]+)"
)
RE_FATOR_R = re.compile(r"Fator r\s*=\s*(.+)")
RE_SUBLIMITE = re.compile(r"Sublimite de Receita Anual \(R\$\):\s*([\d.,]+)")

# ---------------------------------------------------------------------------
# Regex — blocos de atividade
# ---------------------------------------------------------------------------
MARCADOR_ATIVIDADE = "Valor do Débito por Tributo para a Atividade (R$):"
# Fim da área de atividades — não depende do prefixo numérico da seção
# (pode variar entre exercícios do PGDAS-D).
RE_FIM_ATIVIDADES = re.compile(r"Informações sobre DAS Gerado")

RE_RECEITA_ATIVIDADE = re.compile(r"Receita Bruta Informada:\s*R\$\s*([\d.,]+)")
RE_LINHA_TRIBUTOS = re.compile(
    r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+"
    r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)"
)  # IRPJ CSLL COFINS PIS INSS ICMS IPI ISS Total — 9 valores em sequência
RE_ST = re.compile(r"Substituição tributária de:\s*(.+?)\.")
RE_MONO = re.compile(r"Tributação monofásica de:\s*(.+?)\.")

# ---------------------------------------------------------------------------
# Regex — seção do DAS gerado
# ---------------------------------------------------------------------------
RE_DAS_PRINCIPAL = re.compile(r"Principal\s+([\d.,]+)")
RE_DAS_LINHA1 = re.compile(
    r"IRPJ\s+([\d.,]+)\s+CSLL\s+([\d.,]+)\s+COFINS\s+([\d.,]+)\s+PIS/PASEP\s+([\d.,]+)"
)
RE_DAS_LINHA2 = re.compile(
    r"INSS/CPP\s+([\d.,]+)\s+ICMS\s+([\d.,]+)\s+IPI\s+([\d.,]+)\s+ISS\s+([\d.,]+)"
)


def _to_decimal(texto: str) -> Decimal:
    """Converte '1.502.383,95' -> Decimal('1502383.95')."""
    limpo = texto.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation as exc:
        raise PGDASParserError(f"valor numérico inválido: {texto!r}") from exc


def _buscar_obrigatorio(padrao: "re.Pattern", texto: str, nome_campo: str) -> str:
    match = padrao.search(texto)
    if not match:
        raise PGDASParserError(f"campo obrigatório não encontrado no extrato: {nome_campo}")
    return match.group(1).strip()


def _extrair_texto(caminho_pdf: str) -> str:
    """Extrai o texto do PDF via `pdftotext -layout` (subprocess)."""
    if not os.path.isfile(caminho_pdf):
        raise PGDASParserError(f"arquivo não encontrado: {caminho_pdf}")
    try:
        resultado = subprocess.run(
            ["pdftotext", "-layout", caminho_pdf, "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise PGDASParserError(
            "pdftotext não encontrado no PATH — instale o poppler (poppler-utils)"
        ) from exc
    if resultado.returncode != 0:
        raise PGDASParserError(f"falha ao extrair texto do PDF: {resultado.stderr}")
    return resultado.stdout


def _extrair_blocos_atividade(texto_atividades: str) -> List[BlocoAtividade]:
    """Divide o texto pelos marcadores de atividade — detecta 1..N blocos, nunca hardcoded."""
    partes = texto_atividades.split(MARCADOR_ATIVIDADE)[1:]
    if not partes:
        raise PGDASParserError("nenhum bloco de atividade encontrado no extrato")

    blocos = []
    for bloco_texto in partes:
        receita_texto = _buscar_obrigatorio(
            RE_RECEITA_ATIVIDADE, bloco_texto, "receita bruta informada da atividade"
        )
        linha = RE_LINHA_TRIBUTOS.search(bloco_texto)
        if not linha:
            raise PGDASParserError("linha de tributos da atividade não encontrada no extrato")
        irpj, csll, cofins, pis, inss_cpp, icms, ipi, iss, total = (
            _to_decimal(v) for v in linha.groups()
        )

        descricao = re.sub(r"\s+", " ", bloco_texto.split("Receita Bruta Informada:")[0]).strip()

        st_match = RE_ST.search(bloco_texto)
        mono_match = RE_MONO.search(bloco_texto)
        tributos_st = (
            [t.strip() for t in st_match.group(1).split(",")] if st_match else []
        )
        tributos_monofasicos = (
            [t.strip() for t in mono_match.group(1).split(",")] if mono_match else []
        )

        blocos.append(
            BlocoAtividade(
                descricao=descricao,
                receita_bruta_informada=_to_decimal(receita_texto),
                irpj=irpj,
                csll=csll,
                cofins=cofins,
                pis=pis,
                inss_cpp=inss_cpp,
                icms=icms,
                ipi=ipi,
                iss=iss,
                total=total,
                com_substituicao_tributaria=st_match is not None,
                com_tributacao_monofasica=mono_match is not None,
                tributos_st=tributos_st,
                tributos_monofasicos=tributos_monofasicos,
            )
        )
    return blocos


def parsear_texto_pgdas(texto: str) -> ExtratoPGDAS:
    """Estrutura o texto já extraído do PDF em `ExtratoPGDAS`.

    Separado de `parsear_pgdas` para poder ser testado diretamente com uma
    string, sem depender de um PDF real em disco.
    """
    cnpj_basico = _buscar_obrigatorio(RE_CNPJ, texto, "CNPJ Básico")
    razao_social = _buscar_obrigatorio(RE_RAZAO, texto, "Nome Empresarial")
    municipio = _buscar_obrigatorio(RE_MUNICIPIO, texto, "Município")
    uf = _buscar_obrigatorio(RE_UF, texto, "UF")
    periodo_apuracao = _buscar_obrigatorio(RE_PA, texto, "Período de Apuração")
    rpa = _to_decimal(_buscar_obrigatorio(RE_RPA, texto, "Receita Bruta do PA (RPA)"))
    rbt12 = _to_decimal(_buscar_obrigatorio(RE_RBT12, texto, "RBT12"))
    sublimite_receita_anual = _to_decimal(
        _buscar_obrigatorio(RE_SUBLIMITE, texto, "Sublimite de Receita Anual")
    )

    fator_r_texto = _buscar_obrigatorio(RE_FATOR_R, texto, "Fator r")
    if fator_r_texto.strip().lower().startswith("não se aplica"):
        fator_r = None
    else:
        fator_r = _to_decimal(fator_r_texto)

    fim_match = RE_FIM_ATIVIDADES.search(texto)
    texto_atividades = texto[: fim_match.start()] if fim_match else texto
    texto_das = texto[fim_match.start():] if fim_match else ""
    blocos_atividade = _extrair_blocos_atividade(texto_atividades)

    if not texto_das:
        raise PGDASParserError("seção de DAS gerado não encontrada no extrato")

    linha1 = RE_DAS_LINHA1.search(texto_das)
    linha2 = RE_DAS_LINHA2.search(texto_das)
    if not linha1 or not linha2:
        raise PGDASParserError("linhas de composição do DAS não encontradas no extrato")
    das_irpj, das_csll, das_cofins, das_pis = (_to_decimal(v) for v in linha1.groups())
    das_inss_cpp, das_icms, das_ipi, das_iss = (_to_decimal(v) for v in linha2.groups())
    das_total = _to_decimal(_buscar_obrigatorio(RE_DAS_PRINCIPAL, texto_das, "DAS Principal"))

    return ExtratoPGDAS(
        cnpj_basico=cnpj_basico,
        razao_social=razao_social,
        municipio=municipio,
        uf=uf,
        periodo_apuracao=periodo_apuracao,
        rpa=rpa,
        rbt12=rbt12,
        fator_r=fator_r,
        sublimite_receita_anual=sublimite_receita_anual,
        blocos_atividade=blocos_atividade,
        das_total=das_total,
        das_irpj=das_irpj,
        das_csll=das_csll,
        das_cofins=das_cofins,
        das_pis=das_pis,
        das_inss_cpp=das_inss_cpp,
        das_icms=das_icms,
        das_ipi=das_ipi,
        das_iss=das_iss,
    )


def parsear_pgdas(caminho_pdf: str) -> ExtratoPGDAS:
    """Extrai texto do PDF via pdftotext e devolve o extrato estruturado."""
    return parsear_texto_pgdas(_extrair_texto(caminho_pdf))
