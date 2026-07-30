"""Constantes da LC 214/2025 (reforma tributária do consumo).

Concentra alíquotas de referência de IBS/CBS, definição dos regimes
tributários contemplados (Simples Nacional, Lucro Presumido, Lucro Real)
e o cronograma de transição entre o sistema atual e o novo IVA dual,
conforme Art. 128, 343, 344 e 346 da LC 214/2025.
"""

from decimal import Decimal
from enum import Enum
from typing import Dict

D = Decimal


class Regime(str, Enum):
    SIMPLES = "simples"
    PRESUMIDO = "presumido"
    REAL = "real"


class Setor(str, Enum):
    """11 setores com redução de 60% (Art. 128, LC 214/2025) + PADRAO (0%)."""

    PADRAO = "padrao"
    EDUCACAO = "educacao"
    SAUDE = "saude"
    DISPOSITIVOS_MED = "dispositivos_med"
    ACESSIBILIDADE = "acessibilidade"
    MEDICAMENTOS = "medicamentos"
    ALIMENTOS = "alimentos"
    HIGIENE_BAIXA_RENDA = "higiene_baixa_renda"
    AGROPECUARIO = "agropecuario"
    CULTURAL = "cultural"
    DESPORTIVO = "desportivo"
    SEGURANCA_NAC = "seguranca_nac"


class FluxoComercial(str, Enum):
    B2B = "b2b"
    B2C = "b2c"
    MISTO = "misto"


# Alíquotas 2026 [Art. 343 e 346, LC 214/2025]
ALIQUOTAS_2026: Dict[str, Decimal] = {
    "ibs_estadual": D("0.001"),
    "ibs_municipal": D("0.000"),
    "cbs": D("0.009"),
}

# Alíquotas 2027-2028 [Art. 344 e 347, LC 214/2025]
# CBS = alíquota de referência estimada (8,8%) menos 0,1 p.p. [Art. 347]
# PLACEHOLDER: alíquota de referência ainda não fixada por Resolução do Senado [Art. 18]
ALIQUOTAS_2027_2028: Dict[str, Decimal] = {
    "ibs_estadual": D("0.0005"),
    "ibs_municipal": D("0.0005"),
    "cbs": D("0.088") - D("0.001"),
}

# Alíquotas de referência plenas (2029+) [Art. 18, Art. 361-365, LC 214/2025]
# PLACEHOLDER: valores estimados até publicação da Resolução do Senado [Art. 18]
CBS_REFERENCIA_PLENA: Decimal = D("0.088")
IBS_REFERENCIA_PLENA: Decimal = D("0.177")

# Teto indicativo da carga tributária combinada [Art. 475 §11]
TETO_INDICATIVO: Decimal = D("0.265")

# Redução por setor [Art. 128, LC 214/2025] — 60% uniforme para os 11 setores
# listados; PADRAO não tem redução. Gerado a partir do enum (e não listado
# setor a setor) para impedir que um valor diferente de 0%/60% seja
# introduzido por engano.
REDUCAO_SETOR: Dict[Setor, Decimal] = {
    Setor.PADRAO: D("0.00"),
    **{setor: D("0.60") for setor in Setor if setor != Setor.PADRAO},
}

# Cronograma de redução de ICMS/ISS [Art. 501 e 508, LC 214/2025]
# ICMS e ISS ficam intocados até 2028; redução gradual só começa em 2029.
CRONOGRAMA_REDUCAO_ICMS_ISS: Dict[int, Decimal] = {
    2026: D("0.00"),
    2027: D("0.00"),
    2028: D("0.00"),
    2029: D("0.10"),
    2030: D("0.20"),
    2031: D("0.30"),
    2032: D("0.40"),
    2033: D("1.00"),
}

# PIS/COFINS [Art. 345, LC 214/2025]
# 2026 é o último ano intocado; a partir de 2027 são substituídos pela CBS.
ANO_LIMITE_PIS_COFINS: int = 2026

# Alíquotas PIS/COFINS atuais
PIS_COFINS_CUMULATIVO: Decimal = D("0.0365")  # 0,65% + 3,00% — Presumido/Simples
PIS_COFINS_NAO_CUMULATIVO: Decimal = D("0.0925")  # 1,65% + 7,60% — Lucro Real

# Limites do Simples Nacional [LC 123/2006, Art. 3º]
LIMITE_SIMPLES_ANUAL: Decimal = D("4800000.00")
LIMITE_MEI_ANUAL: Decimal = D("81000.00")

_ANO_MIN, _ANO_MAX = 2026, 2033


class RegrasCredito:
    """Regras de apropriação de crédito de entrada [Art. 47, LC 214/2025]."""

    REGIME_REGULAR: Decimal = D("1.00")  # Art. 47 caput — crédito integral
    ISENTO: Decimal = D("0.00")  # Art. 49 — sem direito a crédito

    @staticmethod
    def calcular_credito_simples(valor_compra: Decimal, aliquota_das: Decimal) -> Decimal:
        """Art. 47 §9º II — crédito ao adquirente proporcional ao IBS/CBS
        efetivamente recolhido pelo optante do Simples via DAS."""
        return (valor_compra * aliquota_das).quantize(D("0.01"))


def get_aliquotas_ano(ano: int, setor: Setor = Setor.PADRAO) -> Dict[str, Decimal]:
    """Retorna cbs, ibs, total e fase para o ano/setor informados.

    Aplica a redução setorial [Art. 128] sobre a alíquota antes de somar
    cbs + ibs em "total".
    """
    if not (_ANO_MIN <= ano <= _ANO_MAX):
        raise ValueError(
            f"Ano {ano} fora do intervalo válido da LC 214/2025 ({_ANO_MIN}-{_ANO_MAX})"
        )

    if ano == 2026:
        cbs = ALIQUOTAS_2026["cbs"]
        ibs = ALIQUOTAS_2026["ibs_estadual"] + ALIQUOTAS_2026["ibs_municipal"]
        fase = "2026"
    elif ano in (2027, 2028):
        cbs = ALIQUOTAS_2027_2028["cbs"]
        ibs = ALIQUOTAS_2027_2028["ibs_estadual"] + ALIQUOTAS_2027_2028["ibs_municipal"]
        fase = "2027-2028"
    else:
        cbs = CBS_REFERENCIA_PLENA
        ibs = IBS_REFERENCIA_PLENA
        fase = "2029+"

    reducao = REDUCAO_SETOR[setor]  # Art. 128 — aplicado à alíquota, não à base de cálculo
    cbs_final = cbs * (D("1") - reducao)
    ibs_final = ibs * (D("1") - reducao)
    return {"cbs": cbs_final, "ibs": ibs_final, "total": cbs_final + ibs_final, "fase": fase}


def get_reducao_icms_iss(ano: int) -> Decimal:
    """Retorna o percentual de redução de ICMS/ISS no ano [Art. 501 e 508]."""
    if ano not in CRONOGRAMA_REDUCAO_ICMS_ISS:
        raise ValueError(
            f"Ano {ano} fora do intervalo válido da LC 214/2025 ({_ANO_MIN}-{_ANO_MAX})"
        )
    return CRONOGRAMA_REDUCAO_ICMS_ISS[ano]
