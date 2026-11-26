# ADR 0034: Chat com LLM local sobre a gold

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O painel mostra métricas fixas. Faltava uma forma de fazer perguntas e análises livres sobre os dados, sem expor dado pessoal (ADR 0005, 0010).

## Decisão

- **Modelo local:** Ollama (`qwen2.5:7b-instruct` por padrão, `OLLAMA_MODEL`), com tool calling. Por padrão nenhum dado sai da máquina (servidor remoto só se configurado, ver Infra).
- **Agente sem framework** (`src/chat/agente.py`): laço de até 6 chamadas ao modelo, com duas ferramentas para o modelo: `consultar_sql` (só SELECT) e `buscar_documentos` (a busca híbrida do ADR 0011). O esquema (catálogo e `COMMENT ON`, via `descrever_esquema`) já vai no prompt de sistema.
- **Defesa no banco:** usuário `observatorio_chat` (migração 0033), que herda `observatorio_leitura`, com `default_transaction_read_only` e `statement_timeout` de 10 s. Lê só `gold`, `dbt_marts` e `busca`. A validação do SQL em `src/chat/ferramentas.py` é segunda camada e usa o parser do próprio PostgreSQL (`pglast`, que embute o `libpg_query`): aceita um único SELECT/WITH, só sobre relações `gold`, `dbt_marts` e `busca` sempre qualificadas (ou CTEs do próprio comando), sem escrita em CTE, `SELECT INTO` ou `FOR UPDATE`, só com funções de uma lista de permissão (agregados, janelas, texto, número, data e busca textual; as dos esquemas `gold`/`busca` valem pelo esquema), e sem colunas pessoais. O resultado é lido por cursor do lado do servidor, cortado em 200 linhas, para uma consulta enorme não ocupar a memória do painel; `repeat`, `lpad` e `rpad` ficam fora da lista por alocarem até 1 GB. Nome de CTE só vale onde o PostgreSQL o enxerga (escopo por `WITH`), para um nome solto não cair no `search_path`. Como valida a árvore, e não o texto, comentários, literais, aspas, `U&` e `E''` são lidos como o servidor os lê (a versão anterior, por regex, perdeu para `\r` em comentário e para aspas em identificador). Segue sendo segunda camada: quem segura é o papel do banco. `CHAT_DATABASE_URL` recusa hosts do Supabase.
- **Limite conhecido:** a gold tem células com menos de 5 (ex.: `total_cotistas` em cursos pequenos); o chat não as mascara, então não afirma k >= 5. Mascarar na gold fica como melhoria.
- **Interface:** assistente flutuante no canto inferior direito do painel (`src/dashboard/assistente.py`), com o SQL executado visível. Não existe na versão estática (stlite).
- **Infra:** serviço `ollama` no profile `chat` do `docker-compose.yml`, com imagem fixada (`OLLAMA_IMAGE_TAG`). `scripts/chat.sh` detecta GPU NVIDIA/AMD e aplica o override `docker-compose.gpu-*.yml`; sem GPU, CPU. `OLLAMA_URL` (+ `OLLAMA_API_KEY`; `OLLAMA_URL_REMOTO` no compose) permite usar um servidor ou cluster remoto com API do Ollama: nesse caso os resultados das consultas saem da máquina, então só vale para infraestrutura da instituição.
- **Credencial do papel:** a migração 0033 cria `observatorio_chat` `NOLOGIN`, sem senha; `src/db/migrar.py` habilita o login com a senha de `CHAT_DATABASE_URL`, e só se o host dessa URL for o do banco migrado (assim nenhum banco remoto recebe credencial conhecida).
- **Contexto:** o histórico enviado ao modelo é podado a 24 mensagens (prompt de sistema + últimas rodadas), por causa do `num_ctx` de 8192.

## Consequências

- Um modelo de 7B pode errar o SQL; o erro do banco volta ao modelo, que tenta de novo, e o SQL fica visível para conferência.
- `buscar_documentos` conecta com o usuário do chat (`CHAT_DATABASE_URL`), como `consultar_sql`: nenhuma ferramenta usa o dono do banco.
- Contra vazamento: `validar_sql` recusa toda função fora da lista de permissão (`pg_read_file`, `dblink`, `query_to_xml`, `ts_stat`... não precisam ser citadas) e colunas pessoais (`matricula`, `cpf`, `email`...), na árvore do SQL e nas colunas devolvidas.
- Contra alucinação: `src/chat/verificacao.py` confere se cada número da resposta aparece nos resultados das ferramentas, na pergunta ou no esquema; os sem fonte vão em `avisos` e a página mostra um alerta. É heurística (não barra a resposta), e o SQL continua visível para conferência.
- Guardrails (`src/chat/guardrails.py`), regras fixas e sem segundo LLM (em CPU cada chamada extra custa minutos, e um juiz de 7B erra tanto quanto o agente). Entrada, antes do modelo: recusa pergunta vazia ou com mais de 1000 caracteres, injeção de prompt, pedido de alterar ou apagar dados (`DROP`, `DELETE`...), pedido de dado de pessoa e assunto fora do Observatório; a pergunta barrada não entra no histórico. Saída: resposta em chinês ou que cite tabela, SQL, ferramenta ou prompt é refeita uma vez; se persistir, o usuário vê uma mensagem segura. CPF e e-mail na resposta são mascarados. Cada bloqueio de entrada vai para o log. Limite: regex não pega injeção bem disfarçada, por isso o papel do banco continua sendo a defesa real.
- Texto de `busca.documentos` é tratado como dado, não instrução (prompt injection), e o papel somente leitura limita o dano.
- Pendente: conjunto de perguntas de referência para medir acerto do modelo, como em `tests/test_banco_busca.py`.
