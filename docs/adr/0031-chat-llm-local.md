# ADR 0031: Chat com LLM local sobre a gold

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O painel mostra métricas fixas. Faltava uma forma de fazer perguntas e análises livres sobre os dados, sem expor dado pessoal (ADR 0005, 0010).

## Decisão

- **Modelo local:** Ollama (`qwen2.5:7b-instruct` por padrão, `OLLAMA_MODEL`), com tool calling. Nenhum dado sai da máquina.
- **Agente sem framework** (`src/chat/agente.py`): laço de até 6 chamadas ao modelo, com três ferramentas: `descrever_esquema` (catálogo e `COMMENT ON`), `consultar_sql` (só SELECT) e `buscar_documentos` (a busca híbrida do ADR 0011).
- **Defesa no banco:** usuário `observatorio_chat` (migração 0027), que herda `observatorio_leitura`, com `default_transaction_read_only` e `statement_timeout` de 10 s. Lê só `gold`, `dbt_marts` e `busca`. A validação do SQL em `src/chat/ferramentas.py` (um comando, SELECT/WITH, sem bronze/silver) é segunda camada, por heurística de texto.
- **Interface:** página Streamlit `src/dashboard/pages/chat.py`, com o SQL executado visível. Não existe na versão estática (stlite).
- **Infra:** serviço `ollama` no profile `chat` do `docker-compose.yml`.

## Consequências

- Um modelo de 7B pode errar o SQL; o erro do banco volta ao modelo, que tenta de novo, e o SQL fica visível para conferência.
- `buscar_documentos` usa `src.busca.buscar`, que conecta com `DATABASE_URL` (dono do banco), e não com o usuário do chat. Só lê `busca.documentos`; migrar para o usuário do chat é uma melhoria pendente.
- Texto de `busca.documentos` é tratado como dado, não instrução (prompt injection), e o papel somente leitura limita o dano.
- Pendente: conjunto de perguntas de referência para medir acerto do modelo, como em `tests/test_banco_busca.py`.
