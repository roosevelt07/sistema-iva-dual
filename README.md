# Sistema IVA Dual

Simulador comparativo IBS/CBS (IVA Dual) — LC 214/2025.

Analisa regimes tributários (Simples Nacional, Lucro Presumido, Lucro Real)
e recomenda migração ou manutenção do regime atual com base em carga líquida,
crédito de entrada e cronograma de transição 2026-2033.

> ⚠️ **Projeto em desenvolvimento ativo** — funcionalidades sendo adicionadas e validadas.

## Stack
- Python 3.9+ · Pydantic v2 · Streamlit · Plotly
- python-docx · python-pptx · loguru · pytest

## Como rodar
```bash
pip install -e .
PYTHONPATH=. streamlit run app.py
```

## Testes
```bash
pytest tests/ -v
```

## Status
- [x] Motor de cálculo IBS/CBS (57 testes)
- [x] Comparativo de regimes: Simples / Presumido / Real
- [x] Interface Streamlit 3 modos
- [x] Exportação Word e PPT
- [ ] Parser de documentos Receita/Sefaz
- [ ] Módulo alíquotas DAS por anexo Simples (aguarda tabela CGSN)
- [ ] Alíquotas de referência definitivas (aguarda Resolução do Senado)

## Base legal
LC 214/2025 · EC 132/2023 · LC 123/2006
