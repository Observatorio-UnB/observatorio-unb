# Como a origem trata histórico (E1)

**A origem sobrescreve.** A cada carga mensal, a Silver 3NF, o OLTP do projeto, é substituída por inteiro pelo conteúdo do arquivo mais recente do portal: `TRUNCATE` e `INSERT ... SELECT` numa transação (`src/db/povoar_silver_3nf.py`). A bronze, que vem antes dela, também (`src/db/tabelas.py`, `gravar_varias`). Não é um CRUD linha a linha, porque ninguém faz `UPDATE` num vínculo. Mas o efeito é o mesmo: **o valor anterior de cada linha some na carga seguinte.**

A única tabela insert-only é o registro das cargas (`silver.cargas_vinculos` e `silver.cargas_vinculos_retrato`, migração 0021). Ele guarda, a cada carga, contagens agregadas, e não as linhas.

A decisão e as alternativas estão no [ADR 0032](adr/0032-modelagem-do-sistema-de-origem.md).

## Por que sobrescrever

A própria fonte sobrescreve. O SIGAA e o SIGRA publicam um extrato do estado **atual** de cada vínculo: a situação de hoje (`status_aluno`), a forma de saída e o registro do diploma. Eles não publicam a sequência de situações pela qual o aluno passou. Um esquema insert-only no OLTP guardaria uma cópia inteira do arquivo a cada publicação: cerca de 196 mil linhas e 56 MB na bronze por publicação, contra cerca de 2 MB de vínculos novos por ano (ver [caracterização da carga](caracterizacao_da_carga.md)). O histórico que isso daria seria só a diferença entre duas fotos, e não o histórico real do aluno.

E a pergunta de gestão não precisa dele. *"Em quais cursos a retenção e o atraso são mais críticos?"* se responde com o **desfecho** de cada vínculo das coortes maduras: ingresso, saída e forma de saída. Esses dados estão na foto atual, e cada vínculo já carrega o próprio tempo de evento.

## Onde o histórico existe, e de quê

| Onde | Guarda | Como | Desde |
|---|---|---|---|
| Cada linha de `silver.movimentacoes_vinculos` | O tempo de evento do vínculo: ano de ingresso, ano e semestre de saída, permanência | Vem da fonte. É por isso que dá para analisar coortes de 2000 em diante com uma foto só | E1 |
| `silver.cargas_vinculos` + `_retrato` (insert-only) | Por carga: data de publicação do arquivo, marca d'água e quantos vínculos há por ano de ingresso, desfecho e período de saída | Uma linha por carga. O pipeline nunca apaga; só `demonstrar_dado_atrasado.py` remove as cargas simuladas que ele mesmo cria | E2 ([ADR 0026](adr/0026-dado-atrasado-marca-dagua.md)) |
| `dbt_snapshots.snap_atributos_curso` → `dim_curso` (SCD tipo 2) | Os atributos de classificação de cada curso (grau, área, departamento, tronco), com vigência | Uma versão nova quando um atributo muda | E3 ([ADR 0028](adr/0028-dim-curso-scd-tipo-2.md)) |
| Lago Delta (`data/lake/`) | As versões das tabelas exportadas | Viagem no tempo do Delta, por 7 dias (VACUUM) | E2 ([ADR 0024](adr/0024-lago-delta-parquet-zstd.md)) |
| `bronze.ingestoes` | Só o **último** download de cada recurso (URL, data, sha256, linhas) | `ON CONFLICT (tabela) DO UPDATE` | E2 |

## O que isso permite perguntar

- Taxa de evasão, de formatura e atraso médio de cada curso, por coorte de ingresso, desde 2000. Usa o tempo de evento de cada vínculo.
- Quantos vínculos de cada coorte chegaram atrasados entre uma publicação e a seguinte, e se um número já publicado mudou. Usa o retrato por carga (ADR 0026).
- Desde quando um curso tem a classificação atual, e com qual classificação ele entrou no ranking de um mês anterior. Usa a SCD 2 da `dim_curso`.

## O que isso **não** permite perguntar

- **Qual era a situação de um vínculo numa data passada.** Por exemplo: quantos alunos estavam trancados em 2019. A fonte só dá a situação atual, e a carga sobrescreve a anterior.
- **Quais vínculos, individualmente, mudaram entre duas publicações.** O retrato guarda contagens, e não linhas. Dá para saber quantas formaturas de uma coorte chegaram atrasadas, mas não quais.
- **Reproduzir exatamente o ranking de um mês anterior**, a partir do banco. As métricas são recalculadas a cada carga sobre a foto nova. Só sobram o retrato agregado e, por 7 dias, a versão anterior no lago.

Se a pergunta de gestão passar a exigir alguma dessas, por exemplo acompanhar a trajetória de trancamentos, a origem precisa ficar insert-only. O caminho seria guardar cada publicação na bronze com a data dela, em vez de sobrescrever. Esse é o gatilho de revisão do ADR 0032.

## Carimbos de tempo

Cada tabela guarda um tipo de tempo, e o painel não os mistura:

| Tempo | Onde | Significado |
|---|---|---|
| **Evento** | `ano_ingresso`, `ano_saida`, `semestre_saida` (vínculo) | Quando o aluno entrou e saiu. É o tempo das métricas |
| **Publicação na fonte** | `created` do recurso em `bronze.ingestoes.metadados`; `silver.cargas_vinculos.publicada_em` | Quando o portal publicou o arquivo. É a base da marca d'água do dado atrasado (ADR 0026) |
| **Ingestão** | `bronze.ingestoes.baixado_em` | Quando o pipeline baixou o arquivo |
| **Processamento** | `_carregado_em` (bronze e gold); `gerado_em` da view do painel | Quando a camada foi gravada. É a base do SLA de frescor ([frescor_sla.md](frescor_sla.md)) |
