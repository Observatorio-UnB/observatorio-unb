# ADR 0009: PostgreSQL com migrações versionadas e contrato estrito de carga

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Os arquivos do pipeline mudavam de colunas sem aviso, e quem consumia os dados só descobria depois.

## Decisão

Esquema em `db/migrations/NNNN_*.sql`, aplicado em ordem por `src/db/migrar.py`, com o SHA-256 de cada arquivo em `public.schema_migrations`: editar uma migração já aplicada é erro. `src/db/carregar.py` recusa coluna extra ou coluna obrigatória ausente, e recarrega as camadas numa transação só. O dicionário `docs/dicionario_dados_banco.md` é gerado dos `COMMENT ON`.

## Consequências

Mudança de esquema vira migração nova, revisável. O banco nunca fica com uma camada pela metade. Migrações precisam funcionar tanto em banco vazio quanto em banco já carregado (ex.: DEFAULT, UPDATE e só então DROP DEFAULT).
