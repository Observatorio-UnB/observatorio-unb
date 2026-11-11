# ADR 0001: Arquitetura medalhão (Bronze, Silver, Gold)

- **Status:** Aceita
- **Data:** 2026-08-31

## Contexto

Os CSVs do portal têm encoding, delimitador e grafia de cursos inconsistentes, e parte deles traz dado pessoal. Era preciso separar o dado bruto do dado limpo e do dado publicável.

## Decisão

Três camadas em `data/`: **Bronze** guarda o arquivo como veio do portal; **Silver** limpa, tipa e normaliza (um registro por vínculo); **Gold** agrega por curso e é a única camada publicada. Cada camada é regenerada do zero a cada execução (`scripts/rodar_pipeline.sh`).

## Consequências

Reprocessar é sempre seguro e o CI prova que o pipeline roda numa máquina limpa. Bronze e Silver ficam fora do git (`.gitignore`) por conterem dado pessoal. O custo é baixar e recalcular tudo a cada execução, o que hoje leva poucos minutos.

## Atualização (09/11/2026)

As três camadas continuam, mas saíram de `data/`: desde a migração 0016 cada uma é um esquema do PostgreSQL (`bronze`, `silver`, `gold`), gravado direto no banco e sem arquivo intermediário ([ADR 0009](0009-postgres-migracoes-contrato.md)). A Silver ganhou o modelo em 3NF, e a Gold, o Star Schema. A ordem das etapas agora é o grafo do Dagster ([ADR 0030](0030-modelagem-analitica-e-ferramentas.md)); o `scripts/rodar_pipeline.sh` ficou para o Docker e para quem roda sem o Dagster.
