# Guia de Disponibilização Online do Banco (Supabase), Reconciliação e Governança LGPD

Este documento descreve a arquitetura, o escopo, as salvaguardas de privacidade e os procedimentos operacionais para a disponibilização do banco de dados do **Observatório UnB** no Supabase (PostgreSQL gerenciado em nuvem).

---

## 1. Arquitetura e Decisão de Escopo (LGPD)

O banco em nuvem do Supabase opera como uma **réplica analítica voltada ao consumo público e institucional** (alimentando o dashboard online, o GitHub Pages via dados sincronizados e consultas analíticas seguras).

Conforme formalizado na **[ADR 0031](adr/0031-escopo-disponibilizacao-online-supabase-lgpd.md)** e no **[Registro de Risco de Privacidade](registro_privacidade_lgpd.md)**:

* **Camadas Sincronizadas (Gold e Busca):**
  * `gold.*`: Fatos (`gold.fato_retencao_curso`, `gold.fato_alunos_ativos`, `gold.fato_pibic_perfil`), dimensões conformadas (`dim_curso` com SCD Tipo 2, `dim_tempo`, `dim_campus`, `dim_perfil_social`) e visões materializadas (`mv_dashboard_executivo`).
  * `busca.documentos`: Tabela de busca semântica enriquecida com embeddings vetoriais de alta dimensão gerados pela extensão `vector` (pgvector).
  * **Regra de Privacidade:** Todas as agregações publicadas cumprem o critério de **$k$-anonimato ($k \ge 5$)** ([ADR 0005](adr/0005-privacidade-k-anonimato.md)). Nenhuma métrica identifica alunos isolados.

* **Camadas Restritas (Bronze e Silver):**
  * `bronze.*` e `silver.*`: Contêm dados brutos e normalizados em 3NF com quase-identificadores (curso, data de nascimento, sexo e raça/cor) que atingem **88,93% de unicidade absoluta no SIGRA e 65,63% no SIGAA**.
  * **Isolamento Total:** As tabelas de microdados sensíveis possuem **0 linhas** no Supabase. O processamento dessas camadas é estritamente local (on-premise via Docker Compose).

---

## 2. Controle de Acesso e Segurança

O Supabase aplica o princípio do privilégio mínimo via migração [`0006_controle_de_acesso.sql`](../db/migrations/0006_controle_de_acesso.sql):

1. **Papel `observatorio_leitura`:**
   * Concedido acesso de leitura (`USAGE` e `SELECT`) estritamente nos esquemas `gold` e `busca`.
   * Esquemas `bronze` e `silver` têm todos os privilégios revogados (`REVOKE ALL`).
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

# Sincronização com auditoria e relatório imediato
python3 src/db/sincronizar_supabase.py --verificar
```

### C. Verificar e Reconciliar (Auditoria Automatizada)
Para auditar a saúde, a reconciliação e a conformidade LGPD do Supabase:

```bash
# Execução padrão (saída legível no terminal)
python3 src/db/reconciliar_supabase.py

# Emissão em formato Markdown e persistência das evidências
python3 src/db/reconciliar_supabase.py --salvar-evidencia
```

O script audita:
1. Instalação da extensão `vector` (pgvector);
2. Total de migrações aplicadas no banco remoto;
3. Contagem de microdados na Bronze e Silver (alerta crítico caso haja > 0 linhas);
4. Privilégios do papel `observatorio_leitura`;
5. Reconciliação de contagens das 15 tabelas analíticas sincronizadas;
6. Ocupação do banco frente à cota de 500 MB do plano gratuito.

---

## 5. Manutenção de Frescor e Políticas de Keep-Alive

1. **Keep-Alive Diário (`.github/workflows/supabase-keepalive.yml`):**
   * O plano gratuito do Supabase suspende projetos inativos após 7 dias.
   * O workflow agendado executa diariamente às 12:00 UTC uma consulta na visão materializada analítica (`SELECT count(*) FROM gold.mv_dashboard_executivo;`), garantindo que a instância permaneça ativa.
2. **Atualização Contínua de Frescor (Pipeline de Carga):**
   * A cada execução de `src/db/sincronizar_supabase.py`, o procedimento `CALL gold.atualizar_mv_dashboard_executivo()` é executado no Supabase, renovando os carimbos de `atualizado_em` e `gerado_em` da visão consumida pelo painel.
   * A idade do dado e o cumprimento do SLA de 35 dias podem ser auditados diretamente via consulta SQL (`SELECT now() - max(gerado_em) FROM gold.mv_dashboard_executivo;`), mantendo a rastreabilidade temporal dos dados no consumo.

---

## 6. Procedimento de Rollback e Reversão

Caso seja necessário restaurar ou reverter o estado das tabelas analíticas no Supabase:

1. **Reversão de Carga Incorreta (Truncate Seguro nas Camadas de Consumo):**
   Como as tabelas do Supabase não contêm fontes primárias nem dados brutos não recuperáveis, a camada Gold pode ser limpa sem perda de histórico (pois a origem reside no banco local e nos arquivos do Lago Delta):
   ```sql
   -- No Supabase (via psql ou dashboard SQL)
   TRUNCATE TABLE 
     gold.fato_retencao_curso,
     gold.fato_alunos_ativos,
     gold.fato_pibic_perfil,
     gold.retencao_cursos_unb,
     gold.ativos_hoje_cursos_unb,
     gold.pibic_social_unb,
     gold.inep_benchmark_cursos_unb;
   ```
2. **Repovoamento Limpo:**
   Basta reexecutar a sincronização a partir do banco local íntegro:
   ```bash
   python3 src/db/sincronizar_supabase.py --verificar
   ```

---

## 7. Evidência Atual de Execução e Reconciliação

Resultado da auditoria executada em **02/11/2026**:

| Métrica / Componente | Situação Auditada no Supabase | Status |
| :--- | :---: | :---: |
| **Extensão pgvector** | Versão `0.8.2` instalada | ✅ OK |
| **Migrações Aplicadas** | `23 / 23` (todas as migrações contratuais até a `0025`) | ✅ OK |
| **Microdados de Discentes (LGPD)** | `0` linhas em tabelas de Bronze e Silver | ✅ Conforme |
| **Papel `observatorio_leitura`** | Acesso concedido a `gold` e `busca`; revogado em `bronze`/`silver` | ✅ Seguro |
| **Ocupação em Disco** | `138 MB` consumidos de `500 MB` (27,58% da cota) | ✅ Saudável |
| **Tabelas Analíticas Gold** | 95 cursos de retenção, 118 versões de cursos (SCD2), 12.978 docs com busca vetorial | ✅ Reconciliado |

As evidências completas e detalhadas estão salvas em:
📄 **[`docs/disponibilizacao_online_supabase_evidencias.md`](disponibilizacao_online_supabase_evidencias.md)**

