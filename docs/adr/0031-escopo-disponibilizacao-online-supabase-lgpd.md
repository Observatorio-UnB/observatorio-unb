# ADR 0031: Escopo de disponibilização online do banco no Supabase e salvaguardas de privacidade (LGPD)

- **Status:** Aceita
- **Data:** 2026-11-02

## Contexto

A Entrega 3 (E3) consolida a camada analítica com modelo estrela, transformações dbt e painel gerencial respondendo à pergunta da E1. Para viabilizar o consumo público do painel via internet (deploy no GitHub Pages e consultas analíticas diretas sem exigir que o avaliador ou gestor suba um banco Docker local), a plataforma adota o Supabase (PostgreSQL gerenciado em nuvem) como destino de sincronização.

No entanto, a arquitetura medalhão da plataforma integra dados de discentes da UnB com quase-identificadores e microdados acadêmicos:
- `bronze.sigra_discentes` e `bronze.sigaa_discentes`: trazem nível, curso, data exata de nascimento, sexo e raça/cor. Conforme mensurado no [registro de privacidade](../registro_privacidade_lgpd.md), a unicidade absoluta desses dados atinge **88,93% no SIGRA** e **65,63% no SIGAA** ($k = 1$), permitindo a reidentificação unívoca de alunos por colegas ou terceiros.
- `silver.movimentacoes_vinculos` e `silver.discentes`: contêm o histórico detalhado de cada vínculo, forma de evasão, retenção e anos de permanência.

A issue #35 exige decidir o escopo de disponibilização online: **todo o banco é viável no Supabase? Como garantir a conformidade com a LGPD e os limites de infraestrutura?**

## Alternativas avaliadas

| Critério | Alternativa 1: Disponibilizar Todo o Banco (Bronze, Silver e Gold) | Alternativa 2: Subir Bronze e Silver Anonimizadas/Perturbadas | Alternativa 3 (Escolhida): Subir Estritamente Camadas Agregadas (Gold e Busca) |
|---|---|---|---|
| **Conformidade LGPD (Art. 5º e 6º)** | ❌ **Violação crassa:** expõe microdados identificáveis de discentes em banco acessível pela nuvem pública. | ⚠️ **Risco residual alto:** técnicas de pseudonimização/ruído podem ser revertidas por cruzamento com listas públicas de vestibular e diários oficiais. | ✅ **Minimização por escopo:** microdados individuais permanecem locais; a nuvem recebe apenas dados agregados com $k \ge 5$ ([ADR 0005](0005-privacidade-k-anonimato.md)), conferidos a cada sincronização. |
| **Limite do Plano Gratuito (500 MB)** | ❌ **Inviável:** a descompactação com índices de todas as partições da Silver e arquivos da Bronze estouraria a cota em pouco tempo. | ⚠️ **Crítico:** duplicação de estruturas e índices agregaria overhead próximo do limite de 500 MB. | ✅ **Sustentável:** Gold e busca semântica ocupam apenas **138 MB (27,6% da cota)**, medidos com `pg_database_size()`. |
| **Papéis e Isolamento** | Difícil segregação de privilégios para acesso público do painel. | Complexidade alta de mascaramento dinâmico no PostgreSQL. | Segregação nativa: papel `observatorio_leitura` com `REVOKE` em `bronze` e `silver` ([ADR 0010](0010-controle-de-acesso-leitura.md)). |
| **Esforço de Manutenção** | Complexo (sincronizar milhões de eventos brutos). | Altíssimo (desenvolver rotinas de perturbação e recalcular métricas). | Baixo e robusto: sincronização incremental idempotente (`src/db/sincronizar_supabase.py`). |

## Decisão

1. **Escopo Restrito à Camada de Consumo:** Apenas as tabelas agregadas da **Gold** (Star Schema, visões materializadas e tabelas de benchmarking) e a **Busca Semântica (`busca.documentos` com embeddings pgvector)** são disponibilizadas e sincronizadas no Supabase.
2. **Isolamento Estrito de Microdados (LGPD):** As camadas **Bronze e Silver** com dados individuais de estudantes **NUNCA são sincronizadas para o Supabase**. Ficam armazenadas e processadas exclusivamente no ambiente local/on-premise sob controle de acesso restrito.
3. **Privilégio Mínimo e Controle de Acesso:** O acesso público ao banco em nuvem é segregado pelo papel `observatorio_leitura` (migração `db/migrations/0006_controle_de_acesso.sql`), que possui permissão de leitura exclusivamente nos esquemas `gold` e `busca`, e **nenhum acesso** aos esquemas `bronze` e `silver`. Os papéis da API do Supabase (`anon`, `authenticated`) e o `PUBLIC` também não podem alcançar `bronze` e `silver`, nem pelo esquema nem tabela a tabela.
4. **Auditoria a cada sincronização:** `src/db/reconciliar_supabase.py` confere no Supabase que `bronze` e `silver` não têm linhas, que nenhuma linha da gold agregada tem menos de 5 pessoas ou planos, que os papéis públicos não alcançam `bronze` e `silver` e que as contagens batem com o banco local. Ela roda logo depois da sincronização (`sincronizar_supabase.py --verificar`), no Medalhão e no job mensal do Dagster, e falha a etapa se o veredito não for `APROVADO`. Uma verificação que não consegue ler o dado sai inconclusiva e também reprova.

## Consequências (O que se perde e trade-offs)

- **O que se perde:**
  - Usuários externos conectando-se ao Supabase não conseguem executar consultas analíticas ad-hoc que precisem cruzar atributos no nível do aluno (microdados da 3NF). Essas análises devem ser feitas obrigatoriamente no banco local/docker da Squad.
  - A visualização das tabelas no console do Supabase exibe as tabelas da Bronze e da Silver com contagem zero de registros (as estruturas existem no catálogo porque as migrações DDL são versionadas e uniformes, mas os dados brutos são omitidos intencionalmente).
- **O que se ganha:**
  - Minimização por escopo (LGPD, Lei nº 13.709/2018, art. 6º, III): os quase-identificadores e os dados de renda de discentes não saem do banco local, e a auditoria confere isso a cada sincronização. Não é uma garantia formal de conformidade: o que se publica continua dependendo do k-anonimato da gold (ADR 0005), que a auditoria confere pelo tamanho mínimo de célula, mas não protege contra todo cruzamento entre tabelas agregadas.
  - Preservação da cota de armazenamento: estabilidade em ~138 MB (ocupando 27,6% da cota de 500 MB do Supabase).
  - Disponibilidade para o painel de produção e para a avaliação da monitoria, com credenciais fora do repositório e conexão por SSL, conferida pela auditoria.

## Gatilhos de revisão

- Se a Universidade de Brasília disponibilizar um ambiente institucional de nuvem governamental privada sob sua gestão (DTI/UnB) com homologação de segurança para armazenamento de dados pessoais da comunidade acadêmica.
- Se a banca de avaliação ou os órgãos gestores demandarem autenticação federada (SAML/OAuth com Gov.br ou SIGAA) permitindo controle por perfil de pesquisador autorizado.

