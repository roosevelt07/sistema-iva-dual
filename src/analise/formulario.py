"""Modelos de entrada do formulário de análise.

Define `DadosCliente` (dados brutos informados pelo operador) e
`ContextoCalculo` (dados normalizados/derivados usados pelo motor de
cálculo), como modelos Pydantic.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    computed_field,
    field_validator,
    model_validator,
)

from src.analise.config_lc214 import (
    LIMITE_SIMPLES_ANUAL,
    PIS_COFINS_CUMULATIVO,
    PIS_COFINS_NAO_CUMULATIVO,
    FluxoComercial,
    RegrasCredito,
    Regime,
    Setor,
    get_aliquotas_ano,
    get_reducao_icms_iss,
)

D = Decimal


class DadosCliente(BaseModel):
    """Dados brutos informados pelo operador no formulário de análise."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Bloco 1 — Identificação
    faturamento_anual: Decimal = Field(gt=0)
    regime_atual: Regime
    setor: Setor = Setor.PADRAO
    uf: str
    ano_referencia: int = Field(ge=2026, le=2033)

    # Bloco 2 — Perfil de operações
    percentual_b2b: Decimal = Field(default=D("0.50"), ge=D("0.0"), le=D("1.0"))

    # Bloco 3 — Compras (base de crédito de entrada)
    compras_fornecedor_regime_normal: Decimal  # crédito pleno — Art. 47 caput
    compras_fornecedor_simples: Decimal  # crédito proporcional — Art. 47 §9º
    compras_fornecedor_isento: Decimal  # sem crédito — Art. 49
    aliquota_ibs_cbs_das_fornecedor: Decimal = D("0.005")  # para cálculo Art. 47 §9º

    # Bloco 4 — Tributos atuais (opcionais — fallback para padrão do regime)
    icms_aliquota_efetiva: Optional[Decimal] = None  # None → 19% padrão
    iss_aliquota_efetiva: Optional[Decimal] = None  # None → 5% padrão
    pis_cofins_aliquota_efetiva: Optional[Decimal] = None  # None → padrão do regime

    _alerta_limite_simples: bool = PrivateAttr(default=False)

    @field_validator("uf")
    @classmethod
    def _validar_uf(cls, valor: str) -> str:
        valor = valor.strip().upper()
        if len(valor) != 2 or not valor.isalpha():
            raise ValueError("uf deve ter exatamente 2 letras")
        return valor

    @model_validator(mode="after")
    def _checar_limite_simples(self) -> "DadosCliente":
        # Não bloqueia — apenas sinaliza para o operador (LC 123/2006, Art. 3º)
        if self.regime_atual == Regime.SIMPLES and self.faturamento_anual > LIMITE_SIMPLES_ANUAL:
            object.__setattr__(self, "_alerta_limite_simples", True)
        return self

    @computed_field
    @property
    def percentual_b2c(self) -> Decimal:
        return D("1") - self.percentual_b2b

    @computed_field
    @property
    def fluxo_comercial(self) -> FluxoComercial:
        if self.percentual_b2b == D("1.0"):
            return FluxoComercial.B2B
        if self.percentual_b2b == D("0.0"):
            return FluxoComercial.B2C
        return FluxoComercial.MISTO

    @computed_field
    @property
    def total_compras(self) -> Decimal:
        total = (
            self.compras_fornecedor_regime_normal
            + self.compras_fornecedor_simples
            + self.compras_fornecedor_isento
        )
        return total.quantize(D("0.01"), rounding=ROUND_HALF_UP)

    @computed_field
    @property
    def pis_cofins_padrao(self) -> Decimal:
        if self.pis_cofins_aliquota_efetiva is not None:
            return self.pis_cofins_aliquota_efetiva
        return PIS_COFINS_NAO_CUMULATIVO if self.regime_atual == Regime.REAL else PIS_COFINS_CUMULATIVO

    @computed_field
    @property
    def icms_padrao(self) -> Decimal:
        return self.icms_aliquota_efetiva if self.icms_aliquota_efetiva is not None else D("0.19")

    @computed_field
    @property
    def iss_padrao(self) -> Decimal:
        return self.iss_aliquota_efetiva if self.iss_aliquota_efetiva is not None else D("0.05")

    @computed_field
    @property
    def alerta_limite_simples(self) -> bool:
        return self._alerta_limite_simples


class ContextoCalculo(BaseModel):
    """Dados normalizados para consumo pelos módulos de regime.

    Nunca instanciar diretamente — gerado por `to_contexto()`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identificação
    regime: Regime
    setor: Setor
    uf: str
    ano: int
    faturamento: Decimal

    # Alíquotas efetivas (já com redução de setor aplicada)
    cbs_efetiva: Decimal
    ibs_efetiva: Decimal
    ibs_cbs_total: Decimal
    fase: str

    # Perfil comercial
    percentual_b2b: Decimal
    percentual_b2c: Decimal
    fluxo: FluxoComercial

    # Compras
    compras_regime_normal: Decimal
    compras_simples: Decimal
    compras_isento: Decimal
    aliquota_das_fornecedor: Decimal

    # Tributos atuais
    pis_cofins: Decimal
    icms: Decimal
    iss: Decimal

    # Transição
    reducao_icms_iss_ano: Decimal

    # Crédito de entrada já calculado
    credito_entrada_regime_normal: Decimal
    credito_entrada_simples: Decimal
    credito_entrada_total: Decimal

    # Alertas
    alerta_limite_simples: bool
    alerta_placeholder_senado: bool


def to_contexto(dados: DadosCliente) -> ContextoCalculo:
    """Único ponto de conversão de `DadosCliente` para `ContextoCalculo`."""
    aliquotas = get_aliquotas_ano(dados.ano_referencia, dados.setor)
    reducao_icms_iss = get_reducao_icms_iss(dados.ano_referencia)

    credito_normal = (dados.compras_fornecedor_regime_normal * aliquotas["total"]).quantize(
        D("0.01"), rounding=ROUND_HALF_UP
    )
    credito_simples = RegrasCredito.calcular_credito_simples(
        dados.compras_fornecedor_simples, dados.aliquota_ibs_cbs_das_fornecedor
    )
    credito_total = (credito_normal + credito_simples).quantize(D("0.01"), rounding=ROUND_HALF_UP)

    return ContextoCalculo(
        regime=dados.regime_atual,
        setor=dados.setor,
        uf=dados.uf,
        ano=dados.ano_referencia,
        faturamento=dados.faturamento_anual,
        cbs_efetiva=aliquotas["cbs"],
        ibs_efetiva=aliquotas["ibs"],
        ibs_cbs_total=aliquotas["total"],
        fase=aliquotas["fase"],
        percentual_b2b=dados.percentual_b2b,
        percentual_b2c=dados.percentual_b2c,
        fluxo=dados.fluxo_comercial,
        compras_regime_normal=dados.compras_fornecedor_regime_normal,
        compras_simples=dados.compras_fornecedor_simples,
        compras_isento=dados.compras_fornecedor_isento,
        aliquota_das_fornecedor=dados.aliquota_ibs_cbs_das_fornecedor,
        pis_cofins=dados.pis_cofins_padrao,
        icms=dados.icms_padrao,
        iss=dados.iss_padrao,
        reducao_icms_iss_ano=reducao_icms_iss,
        credito_entrada_regime_normal=credito_normal,
        credito_entrada_simples=credito_simples,
        credito_entrada_total=credito_total,
        alerta_limite_simples=dados.alerta_limite_simples,
        alerta_placeholder_senado=dados.ano_referencia >= 2027,
    )
