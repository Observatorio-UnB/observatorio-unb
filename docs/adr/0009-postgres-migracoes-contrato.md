# ADR 0009: PostgreSQL com migrações versionadas e contrato estrito de carga

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Os arquivos do pipeline mudavam de colunas sem aviso, e quem consumia os dados só descobria depois.

## Decisão

Esquema em `db/migrations/NNNN_*.sql`, aplicado em ordem por `src/db/migrar.py`, com o SHA-256 de cada arquivo em `public.schema_migrations`: editar uma migração já aplicada é erro. `src/db/carregar.py` recusa coluna extra ou coluna obrigatória ausente, e recarrega as camadas numa transação só. O dicionário `docs/dicionario_dados_banco.md` é gerado dos `COMMENT ON`.

## Consequências

Mudança de esquema vira migração nova, revisável. O banco nunca fica com uma camada pela metade. Migrações precisam funcionar tanto em banco vazio quanto em banco já carregado (ex.: DEFAULT, UPDATE e só então DROP DEFAULT).

## Revisão de 2026-11-11: o contrato passou para src/db/tabelas.py

O `src/db/carregar.py` foi removido junto com os CSVs do repositório (commit `48c7875`): nenhuma etapa grava mais arquivo, e cada uma grava a sua camada direto no banco. O contrato continua o mesmo e agora fica em `src/db/tabelas.py`: `gravar` e `gravar_varias` recusam DataFrame com coluna que a tabela não tem ou sem coluna obrigatória (`ErroDeContrato`), e substituem as tabelas numa transação só (TRUNCATE + COPY).
