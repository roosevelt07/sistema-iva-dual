"""Normaliza ExtratoPGDAS para as entradas do motor IBS/CBS e do
cálculo de DAS multi-atividade.

Só converte e valida — nenhum cálculo tributário acontece aqui.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

from src.analise.config_lc214 import Regime, Setor
from src.analise.formulario import DadosCliente
from src.parser.pgdas_parser import BlocoAtividade, ExtratoPGDAS
from src.simples.anexos import Anexo, determinar_anexo_por_fator_r
from src.simples.das_calculado import AtividadeReceita

D = Decimal
RBT12_ALERTA_DESENQUADRAMENTO = D("4320000")  # 90% do teto do Simples (4,8M)


@dataclass
class DadosNormalizados:
    dados_cliente: DadosCliente
    atividades: List[AtividadeReceita]
    anexo_predominante: Anexo
    alertas_normalizacao: List[str]


def _inferir_anexo(bloco: BlocoAtividade, fator_r: Optional[Decimal]) -> Anexo:
    desc = bloco.descricao.lower()
    if "revenda" in desc or "comércio" in desc or "mercadoria" in desc:
        return Anexo.I
    if "indústria" in desc or "industrialização" in desc:
        return Anexo.II
    if "serviço" in desc or "serviços" in desc or "prestação" in desc:
        return determinar_anexo_por_fator_r(fator_r)
    return Anexo.I


def normalizar_extrato(
    extrato: ExtratoPGDAS,
    percentual_b2b: Decimal = D("0.50"),
    compras_regime_normal: Decimal = D("0"),
    compras_simples: Decimal = D("0"),
    compras_isento: Decimal = D("0"),
    aliquota_das_fornecedor: Decimal = D("0.005"),
    ano_referencia: int = 2027,
    setor: Setor = Setor.PADRAO,
) -> DadosNormalizados:
    """Converte `ExtratoPGDAS` em `DadosNormalizados`.

    Campos extraídos automaticamente do extrato: faturamento_anual (usa
    rbt12), regime_atual (sempre Simples — o PGDAS-D é exclusivo dele) e
    uf. Os demais são informados pelo operador via parâmetros.
    """
    atividades = [
        AtividadeReceita(
            nome=bloco.descricao,
            anexo=_inferir_anexo(bloco, extrato.fator_r),
            receita_atividade=bloco.receita_bruta_informada,
            com_st_ou_monofasico=(
                bloco.com_substituicao_tributaria or bloco.com_tributacao_monofasica
            ),
        )
        for bloco in extrato.blocos_atividade
    ]
    receita_por_anexo: dict = defaultdict(lambda: D("0"))
    for a in atividades:
        receita_por_anexo[a.anexo] += a.receita_atividade
    anexo_predominante = max(receita_por_anexo, key=lambda k: receita_por_anexo[k])

    dados_cliente = DadosCliente(
        faturamento_anual=extrato.rbt12,
        regime_atual=Regime.SIMPLES,
        setor=setor,
        uf=extrato.uf,
        ano_referencia=ano_referencia,
        percentual_b2b=percentual_b2b,
        compras_fornecedor_regime_normal=compras_regime_normal,
        compras_fornecedor_simples=compras_simples,
        compras_fornecedor_isento=compras_isento,
        aliquota_ibs_cbs_das_fornecedor=aliquota_das_fornecedor,
    )

    alertas: List[str] = []
    if extrato.fator_r is not None and extrato.fator_r != D("0"):
        alertas.append(f"Fator R = {extrato.fator_r} — verifique se o cliente é Anexo III ou V.")
    for bloco in extrato.blocos_atividade:
        if bloco.com_substituicao_tributaria:
            alertas.append(
                f"Atividade '{bloco.descricao}' tem ST — ICMS/PIS/COFINS já retidos na fonte."
            )
        if bloco.com_tributacao_monofasica:
            tributos = ", ".join(bloco.tributos_monofasicos)
            alertas.append(
                f"Atividade '{bloco.descricao}' tem tributação monofásica de {tributos}."
            )
    if extrato.rbt12 > RBT12_ALERTA_DESENQUADRAMENTO:
        alertas.append(
            "RBT12 próximo do limite do Simples (R$ 4,8M) — risco de desenquadramento."
        )
    if ano_referencia < 2027:
        alertas.append(
            f"Ano {ano_referencia} é período de teste IBS/CBS — alíquotas muito reduzidas, "
            "análise menos relevante."
        )

    return DadosNormalizados(
        dados_cliente=dados_cliente,
        atividades=atividades,
        anexo_predominante=anexo_predominante,
        alertas_normalizacao=alertas,
    )
