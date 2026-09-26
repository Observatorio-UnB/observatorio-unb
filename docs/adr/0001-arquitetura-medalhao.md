# ADR 0001: Arquitetura medalhão (Bronze, Silver, Gold)

- **Status:** Aceita
- **Data:** 2026-08-31

## Contexto

Os CSVs do portal têm encoding, delimitador e grafia de cursos inconsistentes, e parte deles traz dado pessoal. Era preciso separar o dado bruto do dado limpo e do dado publicável.

## Decisão

Três camadas em `data/`: **Bronze** guarda o arquivo como veio do portal; **Silver** limpa, tipa e normaliza (um registro por vínculo); **Gold** agrega por curso e é a única camada publicada. Cada camada é regenerada do zero a cada execução (`scripts/rodar_pipeline.sh`).

## Consequências

Reprocessar é sempre seguro e o CI prova que o pipeline roda numa máquina limpa. Bronze e Silver ficam fora do git (`.gitignore`) por conterem dado pessoal. O custo é baixar e recalcular tudo a cada execução, o que hoje leva poucos minutos.
