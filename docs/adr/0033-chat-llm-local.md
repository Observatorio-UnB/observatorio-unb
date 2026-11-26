# ADR 0033: Chat com LLM local sobre a gold

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O painel mostra métricas fixas. Faltava uma forma de fazer perguntas e análises livres sobre os dados, sem expor dado pessoal (ADR 0005, 0010).

## Decisão

- **Modelo local:** Ollama (`qwen2.5:7b-instruct` por padrão, `OLLAMA_MODEL`), com tool calling. Nenhum dado sai da máquina.
- **Agente sem framework** (`src/chat/agente.py`): laço de até 6 chamadas ao modelo, com três ferramentas: `descrever_esquema` (catálogo e `COMMENT ON`), `consultar_sql` (só SELECT) e `buscar_documentos` (a busca híbrida do ADR 0011).
- **Defesa no banco:** usuário `observatorio_chat` (migração 0032), que herda `observatorio_leitura`, com `default_transaction_read_only` e `statement_timeout` de 10 s. Lê só `gold`, `dbt_marts` e `busca`. A validação do SQL em `src/chat/ferramentas.py` (um comando, SELECT/WITH, sem bronze/silver) é segunda camada, por heurística de texto, e **contornável** (a denylist não vale contra identificadores Unicode escapados, que são recusados, nem contra truques que ainda não conhecemos): quem segura é o papel do banco. `CHAT_DATABASE_URL` recusa hosts do Supabase.
- **Limite conhecido:** a gold tem células com menos de 5 (ex.: `total_cotistas` em cursos pequenos); o chat não as mascara, então não afirma k >= 5. Mascarar na gold fica como melhoria.
- **Interface:** assistente flutuante no canto inferior direito do painel (`src/dashboard/assistente.py`), com o SQL executado visível. Não existe na versão estática (stlite).
- **Infra:** serviço `ollama` no profile `chat` do `docker-compose.yml`.

## Consequências

- Um modelo de 7B pode errar o SQL; o erro do banco volta ao modelo, que tenta de novo, e o SQL fica visível para conferência.
- `buscar_documentos` conecta com o usuário do chat (`CHAT_DATABASE_URL`), como `consultar_sql`: nenhuma ferramenta usa o dono do banco.
- Contra vazamento: `validar_sql` recusa funções de arquivo/sessão (`pg_read_file`, `dblink`, `set_config`...) e colunas pessoais (`matricula`, `cpf`, `email`...), no texto do SQL e nas colunas devolvidas.
- Contra alucinação: `src/chat/verificacao.py` confere se cada número da resposta aparece nos resultados das ferramentas, na pergunta ou no esquema; os sem fonte vão em `avisos` e a página mostra um alerta. É heurística (não barra a resposta), e o SQL continua visível para conferência.
- Texto de `busca.documentos` é tratado como dado, não instrução (prompt injection), e o papel somente leitura limita o dano.
- Pendente: conjunto de perguntas de referência para medir acerto do modelo, como em `tests/test_banco_busca.py`.
