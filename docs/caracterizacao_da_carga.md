# Caracterização da carga de trabalho do sistema de origem (E1, passo 1 do Método de Decisão)

O sistema de origem (OLTP) é a **Silver 3NF** no PostgreSQL: `silver.cursos`, `silver.estruturas_curriculares`, `silver.discentes` e `silver.movimentacoes_vinculos` (migração 0011; [prova da 3NF](arquitetura/01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md)). Ela é populada a partir dos arquivos do portal dados.unb.br, que chegam primeiro à bronze. A modelagem está decidida no [ADR 0032](adr/0032-modelagem-do-sistema-de-origem.md).

Todos os números abaixo foram medidos numa carga do zero, num banco vazio, em 24/11/2026: PostgreSQL 16, as migrações da `main` e o pipeline completo. As consultas usadas estão no fim da página.

## 1. Volume

| Tabela | Linhas | Tamanho (com índices) | O que é uma linha |
|---|---|---|---|
| `silver.movimentacoes_vinculos` | **152.680** | 29 MB, em 3 partições: 2000–2015 (57.982), 2016–2020 (60.105) e 2021–atual (34.593) | Um vínculo de graduação (um aluno num curso) |
| `silver.discentes` | 125.154 | 16 MB | Um aluno (pseudônimo), com nascimento, sexo e raça/cor |
| `silver.cursos` | 158 | 224 kB | Uma oferta de curso do catálogo |
| `silver.estruturas_curriculares` | 112 | 96 kB | Uma matriz por curso canônico, com os prazos |
| `bronze.sigaa_discentes` | 111.385 | 26 MB | Linha do arquivo do SIGAA, como veio |
| `bronze.sigra_discentes` | 85.121 | 30 MB | Linha do arquivo do SIGRA, como veio |
| Banco inteiro (bronze, silver, gold e dbt, sem a vetorização da busca semântica) | — | **205 MB** | — |

**Crescimento.** O que cresce é `movimentacoes_vinculos`, com uma linha nova por ingressante:

| Ano de ingresso | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|
| Vínculos | 10.357 | 11.265 | 12.287 | 12.910 | 13.286 | 10.214 | 10.263 | 9.969 |

São cerca de **10 a 13 mil vínculos por ano**, ou seja, cerca de 2 MB por ano na tabela e menos de 10% de crescimento anual. O ano de 2024 (4.147) ainda está incompleto no arquivo publicado. No ritmo atual, a tabela dobra em cerca de 12 anos. Nesse horizonte, volume não é problema: o recorte inteiro cabe em memória.

## 2. Taxa de escrita

| Quem escreve | Quando | Quanto | Quanto tempo |
|---|---|---|---|
| A própria fonte (portal) | Irregular: SIGAA e SIGRA publicados em 15/07/2024, catálogo de cursos em 24/08/2024, lista de ativos em 17/06/2025, estrutura curricular em 20/10/2020 | Arquivo inteiro a cada publicação (SIGAA 19,5 MB, SIGRA 24,6 MB) | — |
| Pipeline (único escritor do OLTP) | **1 vez por mês**, no dia 1 às 06:00 UTC (`atualiza-dados.yml`) | Recarga completa: 152.680 vínculos + 125.154 discentes + catálogo, numa transação | Silver 3NF em **3,4 s** (mediana de 3 execuções de `povoar_silver_3nf.py`); pipeline inteiro sem a vetorização em cerca de 46 s (ADR 0025) |
| Usuários | Nunca | Nenhuma aplicação escreve no OLTP: não há secretaria lançando vínculo. A fonte de verdade é o SIGAA da UnB, e o portal publica um extrato dele | — |

Em termos de transação, a taxa de escrita é de **cerca de 280 mil linhas por mês, numa única transação em lote**. Não há escrita concorrente nem escrita de usuário. O CDC (ADR 0025) existe para o caso de isso mudar.

## 3. Taxa de leitura

| Quem lê | Como | Frequência |
|---|---|---|
| Pipeline (gold, dbt, lago, export) | Varreduras completas da Silver 3NF, agregando por curso e coorte | 1 vez por mês, logo depois da carga |
| Painel público (GitHub Pages) | **Não lê o banco**: lê o `export/gold.json`, gerado uma vez por publicação | 0 leituras no banco por visita |
| Painel local e Supabase | `observatorio_leitura` nos agregados (`gold`, `dbt_marts`); o snapshot inteiro do painel sai em 0,04 s | Algumas por dia, no uso pela Squad e pela banca |
| Consultas ad hoc (análise, DEG) | Detalhe de um curso e coortes | Esporádicas |

A leitura é rara e quase toda agregada. A consulta mais pesada (contagem de toda a 3NF por curso e desfecho) leva **14 ms**.

## 4. Padrão de acesso

| Padrão | Exemplo | Como o esquema atende |
|---|---|---|
| **Varredura agregada por curso e coorte** (o dominante) | Taxa de evasão de cada curso nas coortes de 2010 a 2016 | Partição por ano de ingresso (poda de partições) e índice `(id_estrutura, tipo_saida_grupo, ano_ingresso)` (migração 0024) |
| Detalhe de um curso | Distribuição de semestres até a formatura de CIENCIA DA COMPUTACAO | O mesmo índice: 14 buffers, 0,42 ms (`docs/explain/`) |
| Busca de curso por nome | "computação" com ou sem acento | GIN com trigramas em `silver.cursos.nome_curso_norm` |
| Escrita | Recarga mensal inteira | `TRUNCATE` + `INSERT ... SELECT` numa transação; sem `UPDATE` linha a linha |

Não há acesso por chave de aluno no consumo: nenhuma consulta de produção pergunta "qual o vínculo do aluno X". O `id_discente` só existe para a 3NF ligar o vínculo à pessoa e para contar alunos distintos.

## 5. Latência tolerada

| O quê | Tolerado | Medido | Por quê |
|---|---|---|---|
| Frescor do dado (fonte → painel) | **Até 35 dias** (SLA, [frescor_sla.md](frescor_sla.md)) | Atualização mensal | A fonte publica no máximo uma vez por ano. Um dado de um mês atrás é tão novo quanto o portal |
| Consulta do painel | Menos de 1 s por tela | Ranking em 0,29 ms; view do painel em 0,38 ms; detalhe de um curso em 0,42 ms (`docs/explain/`); snapshot inteiro em 0,04 s | Uso interativo |
| Carga mensal | Minutos (roda de madrugada, sem ninguém esperando) | Silver 3NF em 3,4 s; pipeline em cerca de 46 s | Sem janela de manutenção a respeitar |
| Disponibilidade da escrita | Uma carga que falha pode ser refeita em dias | Cada etapa tem até 3 retentativas com espera exponencial (Dagster) | Se as retentativas se esgotarem, o SLA de 35 dias dá 4 dias, além do mês, para corrigir à mão. Um dia de atraso não muda nenhuma decisão do DEG |

## 6. O que essa caracterização decide

- **Carga de leitura analítica, sobre um OLTP com um escritor só e escrita em lote mensal.** O que importa no esquema é integridade (a 3NF, com chaves e restrições) e varredura agregada eficiente (partição e índices compostos). Vazão de transações não importa.
- **A recarga completa basta.** A escrita leva 3,4 s por mês. Uma carga incremental economizaria segundos e custaria a lógica de comparar duas publicações do arquivo inteiro para achar o que mudou. A fonte só publica o arquivo completo, sem lista de alterações. Ver o ADR 0032 (histórico) e o ADR 0025 (CDC contra recarga).
- **O volume não justifica motor distribuído.** 205 MB no banco inteiro e crescimento de cerca de 2 MB por ano na maior tabela.

## Como reproduzir as medições

```sql
-- Volume e tamanho
SELECT n.nspname || '.' || c.relname, c.reltuples::bigint, pg_size_pretty(pg_total_relation_size(c.oid))
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('bronze', 'silver') AND c.relkind IN ('r', 'p')
ORDER BY pg_total_relation_size(c.oid) DESC;

-- Crescimento por ano de ingresso
SELECT ano_ingresso, count(*) FROM silver.movimentacoes_vinculos GROUP BY 1 ORDER BY 1;

-- Datas de publicação dos recursos no portal
SELECT i.tabela, r->>'name', left(r->>'created', 10)
FROM bronze.ingestoes i, jsonb_array_elements(i.metadados->'resources') r
WHERE r->>'url' = i.recurso_url;
```

Tempo de escrita: `time python3 src/db/povoar_silver_3nf.py`. Latências de leitura: mediana de 15 execuções de cada consulta, com o cache quente.
