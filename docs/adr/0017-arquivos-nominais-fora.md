# ADR 0017: Arquivos nominais do SIGAA ficam fora da ingestão

- **Status:** Substituída em parte pela [ADR 0020](0020-lista-de-ativos-com-minimizacao.md) (a lista de ativos passou a entrar, minimizada)
- **Data:** 2026-09-26

## Contexto

O pacote de discentes também traz `SIGAA_Concluintes_*` e "SIGAA Ativos", com nome e CPF parcial.

## Decisão

A regex da ingestão do SIGAA só aceita `sigaa.csv` e variantes datadas (`sigaa_AAAA_S.csv`). Há teste garantindo que os arquivos de concluintes não são escolhidos.

## Consequências

Nenhum dado diretamente identificável entra no pipeline. Tudo o que eles trariam de útil (conclusão) já está no `sigaa.csv`.
