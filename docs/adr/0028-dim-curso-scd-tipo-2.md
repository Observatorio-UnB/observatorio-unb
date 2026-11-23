# ADR 0028: `gold.dim_curso` como dimensão de variação lenta tipo 2

- **Status:** Aceita
- **Data:** 2026-11-01

## Contexto

A `gold.dim_curso` era atualizada por sobrescrita (`ON CONFLICT (nome_curso) DO UPDATE`). Os atributos do curso mudam com o tempo. Cada versão nova do catálogo vale por cima da anterior (ADR 0021), e um curso pode trocar de unidade responsável, de área, de grau (bacharelado, licenciatura ou MISTO, ADR 0004) ou passar a ser curso-tronco (ADR 0022). Com a sobrescrita, a mudança apagava o valor anterior. Uma análise por departamento passava a atribuir todo o histórico do curso ao departamento novo, e nada no banco mostrava que a classificação tinha sido outra.

## Decisão

- **SCD tipo 2 com vigência.** A `gold.dim_curso` ganha `vigente_de`, `vigente_ate` e `is_atual` (migração `0025_dim_curso_scd2.sql`). Cada linha é uma versão. A chave natural continua sendo `nome_curso`, e a versão é `(nome_curso, vigente_de)`. Cada versão tem a sua `sk_curso`.
- **Atributos rastreados (tipo 2):** `grau_academico`, `categoria_grau`, `area_conhecimento`, `departamento` e `is_tronco_abi`. A mudança em qualquer um deles fecha a versão atual e abre outra.
- **`id_curso_origem` é tipo 1.** É um ponteiro técnico para a matriz e não classifica o curso. É sobrescrito na versão atual, sem abrir versão.
- **A vigência é o tempo de processamento.** O portal publica só os atributos atuais, sem data de mudança. A versão nova começa na carga que observou a mudança, e a anterior termina no mesmo instante (`now()` da transação da carga).
- **A primeira versão vale desde 21/04/1962**, a fundação da UnB. Como não existe histórico anterior ao início do rastreamento, a primeira versão cobre toda a série. A data é fixa, e não a da carga, para o banco local e o Supabase gerarem a mesma chave `(nome_curso, vigente_de)` sem combinar nada.
- **A carga** (`src/db/povoar_dimensional.py`) roda três comandos na transação do Star Schema: fecha as versões que mudaram, abre versão para quem ficou sem versão atual e sobrescreve o tipo 1. Curso que some da origem continua com a última versão atual: a gold não apaga curso.
- **Os fatos apontam para a versão vigente na carga.** Eles são recriados a cada carga (o grão é um snapshot), e cada um usa a versão atual do curso naquele momento. No Supabase, onde a sincronização não apaga nada, o fato de uma carga antiga continua ligado à versão daquela época. A sincronização casa a dimensão pela versão `(nome_curso, vigente_de)` e religa cada fato à versão exata.
- **Integridade no banco.** `UNIQUE (nome_curso, vigente_de)`. `CHECK` de que a versão fechada termina depois de começar e de que `is_atual` equivale a `vigente_ate` nulo. Uma exclusão (`EXCLUDE ... WHERE is_atual`) garante uma versão atual por curso. Ela é adiada para o commit porque a sincronização fecha a versão antiga e insere a nova num único `INSERT ... ON CONFLICT`, em ordem qualquer.
- **A view do painel lê só a versão atual** (`is_atual` em `gold.mv_dashboard_executivo`). Sem esse filtro, o fato da versão fechada que fica no Supabase faria o curso aparecer duas vezes.

## Alternativas consideradas

- **Tipo 1 (sobrescrita, como antes).** É simples, mas perde o histórico. Foi o problema que motivou esta decisão.
- **Tipo 3 (coluna com o valor anterior).** Guarda só uma mudança por atributo e não diz quando ela aconteceu. Duas reclassificações seguidas perdem a primeira.
- **Tipo 4 (tabela de histórico separada).** A dimensão continuaria sobrescrita e o histórico ficaria numa tabela à parte. Seria preciso juntar as duas para responder "como era em tal data", e os fatos não teriam como apontar para a versão antiga.
- **Vigência pela data de publicação do catálogo** (`publicado_em` da ADR 0021). Seria mais fiel ao tempo de evento, mas o catálogo consolidado da silver mistura campos de versões diferentes (vale o mais recente que preenche cada campo). Uma linha da dimensão não tem uma única data de publicação.

## Consequências

- **A mesma regra vale na camada do dbt.** A `dim_curso` de `transform/` lê o snapshot `snap_atributos_curso` (estratégia `check` nos mesmos cinco atributos, com `vigente_de` e `vigente_ate`). A primeira versão também vale desde 21/04/1962, e o `id_curso_origem` também é tipo 1. Os testes `scd_dim_curso_*` e `scd_fato_aponta_versao_atual` (em `transform/tests/`) conferem uma versão atual por curso, vigências encadeadas sem buraco e o fato na versão atual. `tests/test_dbt_scd2.py` reclassifica um curso numa cópia da silver e confere que a versão anterior continua lá.

- Uma reclassificação preserva a versão anterior e gera uma `sk_curso` nova. A consulta que quer o curso atual precisa filtrar `is_atual`. Os fatos e a view do painel já fazem isso.
- O histórico só existe a partir desta migração. As mudanças anteriores se perderam com a sobrescrita, e toda primeira versão vale desde 1962.
- A renomeação da fonte não abre versão. O nome que importa é o canônico, produzido pela harmonização (ADR 0003): "COMUNICAÇÃO SOCIAL - JORNALISMO" e "JORNALISMO" já chegam como JORNALISMO. Uma mudança do próprio nome canônico vira um curso novo, e o antigo fica com a última versão.
- O lago Delta passou a acompanhar mudança de colunas: a regravação inteira de uma tabela substitui o esquema (`schema_mode="overwrite"`), e coluna nova conta como alteração.
- Testes: `tests/test_banco_scd2.py`. A reclassificação de MATEMATICA abre uma versão sem apagar a anterior, e os fatos e a view passam para a versão nova. A renomeação na matriz mantém o nome antigo com o histórico e leva os fatos ao nome novo. A mudança tipo 1 não abre versão, e a recarga sem mudança não altera nada. A sincronização foi conferida contra um banco local no lugar do Supabase: depois da reclassificação, o destino ficou com as duas versões, o fato antigo ficou na versão antiga e a view mostrou o curso uma vez.
