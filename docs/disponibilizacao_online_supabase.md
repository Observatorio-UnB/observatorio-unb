# Guia de Disponibilização Online do Banco (Supabase), Reconciliação e Governança LGPD

Este documento descreve a arquitetura, o escopo, as salvaguardas de privacidade e os procedimentos operacionais para a disponibilização do banco de dados do **Observatório UnB** no Supabase (PostgreSQL gerenciado em nuvem).

---

## 1. Arquitetura e Decisão de Escopo (LGPD)

O banco em nuvem do Supabase opera como uma **réplica analítica voltada ao consumo público e institucional** (alimentando o dashboard online, o GitHub Pages via dados sincronizados e consultas analíticas seguras).

Conforme formalizado na **[ADR 0031](adr/0031-escopo-disponibilizacao-online-supabase-lgpd.md)** e no **[Registro de Risco de Privacidade](registro_privacidade_lgpd.md)**:

* **Camadas Sincronizadas (Gold e Busca):**
  * `gold.*`: Fatos (`gold.fato_retencao_curso`, `gold.fato_alunos_ativos`, `gold.fato_pibic_perfil`), dimensões conformadas (`dim_curso` com SCD Tipo 2, `dim_tempo`, `dim_campus`, `dim_perfil_social`) e visões materializadas (`mv_dashboard_executivo`).
  * `busca.documentos`: Tabela de busca semântica enriquecida com embeddings vetoriais de alta dimensão gerados pela extensão `vector` (pgvector).
  * **Regra de Privacidade:** As agregações publicadas seguem o critério de **$k$-anonimato ($k \ge 5$)** ([ADR 0005](adr/0005-privacidade-k-anonimato.md)). A auditoria confere, tabela a tabela, que nenhuma linha agregada tem menos de 5 pessoas ou planos.

* **Camadas Restritas (Bronze e Silver):**
  * `bronze.*` e `silver.*`: Contêm dados brutos e normalizados em 3NF com quase-identificadores (curso, data de nascimento, sexo e raça/cor) que atingem **88,93% de unicidade absoluta no SIGRA e 65,63% no SIGAA**.
  * **Minimização por escopo:** bronze e silver não são sincronizadas. As tabelas existem no Supabase, vazias, porque as migrações são as mesmas; a auditoria confere a cada sincronização que todas elas, inclusive as criadas depois, continuam com 0 linhas. O processamento dessas camadas é local (Docker Compose ou runner do CI).

---

## 2. Controle de Acesso e Segurança

O Supabase aplica o princípio do privilégio mínimo via migração [`0006_controle_de_acesso.sql`](../db/migrations/0006_controle_de_acesso.sql):

1. **Papel `observatorio_leitura`:**
   * Concedido acesso de leitura (`USAGE` e `SELECT`) estritamente nos esquemas `gold` e `busca`.
   * Esquemas `bronze` e `silver` têm todos os privilégios revogados (`REVOKE ALL`).
   * A auditoria confere que nem `observatorio_leitura`, nem os papéis da API do Supabase (`anon`, `authenticated`), nem `PUBLIC` têm `USAGE` em `bronze` e `silver` ou `SELECT` em alguma tabela deles.
2. **Criptografia e Transporte Seguro:**
   * Conexões externas ao Supabase devem obrigatoriamente exigir TLS/SSL (`sslmode=require`).
   * As portas utilizadas são `5432` (conexão direta/pooler em modo sessão) e `6543` (pooler transacional via PgBouncer).
3. **Credenciais no Repositório:**
   * Nenhuma credencial ou URL contendo senha é versionada no Git. O acesso remoto depende exclusivamente da variável de ambiente `SUPABASE_DATABASE_URL` ou do GitHub Secret correspondente no CI.

---

## 3. Pré-requisitos e Variáveis de Ambiente

Para operar a sincronização e auditoria, configure as seguintes variáveis no arquivo `.env` da raiz (ou no ambiente):

```bash
# Banco local (pipeline ELT completo)
DATABASE_URL="postgresql://observatorio:observatorio@localhost:5435/observatorio"

# Banco remoto (Supabase - porta 5432 com pooler ou conexão direta)
SUPABASE_DATABASE_URL="postgresql://postgres.[ID_PROJETO]:[SENHA]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
```

---

## 4. Passo a Passo Operacional

### A. Executar as Migrações no Supabase
O gerenciador de migrações da plataforma aplica as migrações versionadas de `db/migrations/` de forma transacional e idempotente:

```bash
python3 -c "from src.db.migrar import aplicar_migracoes; from src.db.conexao import ler_variavel; aplicar_migracoes(ler_variavel('SUPABASE_DATABASE_URL'))"
```

### B. Sincronizar os Dados Analíticos (Gold e Busca)
O script `src/db/sincronizar_supabase.py` compara os dados locais com o Supabase pela chave natural de negócio:
* Linhas novas são inseridas;
* Linhas alteradas são atualizadas (mantendo carimbo `atualizado_em`);
* Linhas idênticas não são regravadas;
* Nenhuma linha é apagada indevidamente;
* Ao final, chama `gold.atualizar_mv_dashboard_executivo()`.

```bash
# Sincronização padrão (inserção + atualização de alterações)
python3 src/db/sincronizar_supabase.py

# Sincronização segura sem atualização de linhas existentes
python3 src/db/sincronizar_supabase.py --somente-inserir

# Sincronização seguida da auditoria (seção C); sai com erro se o veredito não for APROVADO.
# É assim que o Medalhão, o job mensal do Dagster e o rodar_pipeline.sh chamam.
python3 src/db/sincronizar_supabase.py --verificar
```

### C. Verificar e Reconciliar (Auditoria Automatizada)
Para auditar a saúde, a reconciliação e a conformidade LGPD do Supabase:

```bash
# Execução padrão (saída legível no terminal)
python3 src/db/reconciliar_supabase.py

# Relatório completo em Markdown, salvo também em docs/disponibilizacao_online_supabase_evidencias.md
python3 src/db/reconciliar_supabase.py --markdown --salvar-evidencia
```

O script audita:
1. Instalação da extensão `vector` (pgvector);
2. Migrações aplicadas no banco remoto contra `db/migrations/`;
3. Linhas em todas as tabelas de bronze e silver do destino, listadas pelo catálogo, além de uma lista mínima fixa (falha crítica se houver alguma);
4. Tamanho mínimo de célula ($k \ge 5$) nas seis tabelas agregadas da gold (falha crítica se houver linha abaixo);
5. Privilégios de `observatorio_leitura`, `anon`, `authenticated` e `PUBLIC` em bronze e silver, e a leitura de `gold` e `busca` por `observatorio_leitura`;
6. Reconciliação de contagens das 15 tabelas sincronizadas com o banco local (`DATABASE_URL`);
7. Conexão por SSL e ocupação do banco frente à cota de 500 MB do plano gratuito.

O veredito é `APROVADO` só se tudo passar, e o código de saída é 1 em qualquer outro caso. Como a sincronização não apaga linhas, o Supabase pode ter mais linhas que o local (`RECONCILIADO_COM_EXTRAS`, aceito); menos é `DIVERGENTE`. Sem banco local acessível, as tabelas ficam `NAO_VERIFICADO` e o veredito é `REQUER_ATENCAO`. Uma contagem que falha sai `INCONCLUSIVO`, nunca como conforme.

---

## 5. Manutenção de Frescor e Políticas de Keep-Alive

1. **Keep-Alive Diário (`.github/workflows/supabase-keepalive.yml`):**
   * O plano gratuito do Supabase suspende projetos inativos após 7 dias.
   * O workflow agendado executa diariamente às 12:00 UTC uma consulta na visão materializada analítica (`SELECT count(*) FROM gold.mv_dashboard_executivo;`), garantindo que a instância permaneça ativa.
2. **Atualização Contínua de Frescor (Pipeline de Carga):**
   * A cada execução de `src/db/sincronizar_supabase.py`, o procedimento `CALL gold.atualizar_mv_dashboard_executivo()` é executado no Supabase, renovando os carimbos de `atualizado_em` e `gerado_em` da visão consumida pelo painel.
   * A idade do dado e o cumprimento do SLA de 35 dias são conferidos por `src/db/frescor.py`, todo dia, contra o Supabase ([docs/frescor_sla.md](frescor_sla.md)).

---

## 6. Procedimento de Rollback e Reversão

Caso seja necessário refazer do zero as tabelas sincronizadas no Supabase:

1. **Limpeza das tabelas sincronizadas.** São as 14 tabelas de `SINCRONIAS` em `src/db/sincronizar_supabase.py`, num único `TRUNCATE` por causa das chaves estrangeiras entre fatos e dimensões:
   ```sql
   -- No Supabase (via psql ou editor SQL)
   TRUNCATE TABLE
     gold.fato_retencao_curso,
     gold.fato_alunos_ativos,
     gold.fato_pibic_perfil,
     gold.dim_curso,
     gold.dim_campus,
     gold.dim_tempo,
     gold.dim_perfil_social,
     gold.retencao_cursos_unb,
     gold.ativos_hoje_cursos_unb,
     gold.pibic_social_unb,
     gold.inep_benchmark_cursos_unb,
     gold.regras_harmonizacao_canonicas,
     gold.relatorios,
     busca.documentos;
   ```
   A view `gold.mv_dashboard_executivo` continua com o conteúdo antigo até o passo 2, que a atualiza no fim.

   **O que se perde:** o Supabase guarda o que a sincronização nunca apaga, e o banco local não necessariamente tem. Em especial, as versões fechadas da `gold.dim_curso` (SCD tipo 2, [ADR 0028](adr/0028-dim-curso-scd-tipo-2.md)) acumuladas no Supabase. O banco do CI é refeito do zero a cada execução, então só voltam as versões que o banco de origem tiver. Linhas que saíram da origem (curso extinto, relatório renomeado) também não voltam.
2. **Repovoamento:** reexecutar a sincronização a partir do banco local íntegro. Ela aplica as migrações pendentes, copia as tabelas, atualiza a view e roda a auditoria:
   ```bash
   python3 src/db/sincronizar_supabase.py --verificar
   ```

---

## 7. Evidência de Execução

A cada push na `main`, o Medalhão sincroniza, roda a auditoria contra o Supabase com o banco recém-carregado do runner como banco local e publica o relatório completo no resumo da execução (Actions → Medalhão + Pages → *Summary*). Se o veredito não for `APROVADO`, a etapa falha.

Para registrar a evidência no repositório, com os dois bancos acessíveis (`DATABASE_URL` e `SUPABASE_DATABASE_URL`):

```bash
python3 src/db/reconciliar_supabase.py --markdown --salvar-evidencia
```

O resultado fica em 📄 **[`docs/disponibilizacao_online_supabase_evidencias.md`](disponibilizacao_online_supabase_evidencias.md)**.
