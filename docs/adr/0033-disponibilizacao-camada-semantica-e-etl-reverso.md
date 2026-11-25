# ADR 0033: Camada semântica feita à mão no dbt, painel público por arquivo e ETL reverso por push

- **Status:** Aceita
- **Data:** 2026-11-24

## Contexto

A E4 pede o dado disponibilizado de duas formas: o painel e uma camada semântica com a definição de cada métrica num lugar só. Ela também pede que uma métrica tratada volte a um sistema onde alguém age. Os consumidores são três:

- o **painel público**, no GitHub Pages, que roda no navegador (stlite) e não tem acesso ao banco;
- o **painel local e o Supabase**, que leem a gold e os marts pelo papel `observatorio_leitura`;
- a **fila de intervenção** (`operacional.fila_intervencao`), operada pela coordenação de curso e acompanhada pelo DEG.

O dado muda uma vez por mês (a fonte publica no máximo uma vez por ano, ver [caracterização da carga](../caracterizacao_da_carga.md)). As medições abaixo são da carga de 24/11/2026, num banco montado do zero, com mediana de 15 execuções.

## Decisão 1: camada semântica feita à mão no dbt, e não em ferramenta (MetricFlow)

| | Ferramenta (dbt Semantic Layer / MetricFlow) | **À mão no dbt** (escolhida) |
|---|---|---|
| Onde fica a fórmula | YAML de `metrics`, calculado pelo motor na hora da consulta | Uma macro por métrica (`transform/macros/metricas.sql`), usada por todo modelo que publica a métrica |
| Definição versionada | No YAML | `transform/seeds/metricas_definicoes.csv`: 12 métricas com definição, unidade, recortes válidos, versão e ADR |
| Quem consulta | A API do Semantic Layer (dbt Cloud) ou o `mf` local | Tabelas prontas: `painel_cursos_criticos` (94 linhas) e `metricas_por_recorte` (20 linhas) |
| Painel público (sem banco) | Não consulta a API em tempo de execução. Teria de pré-calcular as mesmas tabelas de qualquer jeito | Lê as tabelas exportadas |
| Risco | Infraestrutura e dependência a mais | Divergir: alguém refazer a fórmula fora da macro |

A ferramenta só se paga quando há consumidores fazendo consultas ad hoc que combinam métricas e recortes livremente. Aqui os consumidores leem um conjunto fixo de recortes, e um deles nem tem banco. O risco da solução à mão, que é divergir, é coberto por testes que **falham o build**:

- `metricas_registro_completo`: métrica publicada sem definição, ou o contrário;
- `metricas_recortes_fecham_com_o_painel`: os recortes somam o mesmo que o ranking;
- `TestMesmoNumero`: as abas da gold, o ranking e a fila mostram o mesmo número curso a curso.

O risco é real, e não teórico. Na E4 apareceram três divergências, todas corrigidas:
- a média das taxas no lugar da razão das somas, que dava até 2,88 p.p. de diferença;
- os KPIs da UnB calculados num universo com o curso-tronco (68.339 contra 67.063 ingressantes);
- uma segunda implementação em Python, com 0,01 de diferença.

Ver `docs/camada_semantica_e_etl_reverso.md`.

## Decisão 2: cada consumidor lê pelo caminho mais barato que atende a ele

| Caminho | Medido | Latência do dado | Custo | Acoplamento | Quem usa |
|---|---|---|---|---|---|
| **Banco** (warehouse) | Ranking em 0,23 ms; recortes em 0,11 ms; snapshot inteiro do painel em 44 ms | Imediata | O banco no ar | Ao esquema e ao papel de leitura | Painel local, dbt, ETL reverso |
| **Cópia por arquivo** (`export/gold.json`) | 1.034 KB; gerado em 50 ms; lido pelo painel em 4 ms | A do último export (a cada push na `main` e no agendamento mensal) | Nenhum serviço: GitHub Pages | Só ao formato do JSON | **Painel público** |
| **Banco gerenciado** (Supabase) | Gold + busca: 138 MB, 27,6% da cota de 500 MB (ADR 0031). Latência de rede não medida daqui | A da sincronização incremental | Plano gratuito | Ao esquema da gold | Consultas SQL de fora, pelo papel de leitura |
| Federação de consultas | — | — | — | — | Não usada: não há uma segunda base para federar. O INEP é ingerido na bronze |

O painel público lê uma **cópia por arquivo** porque roda no navegador de quem visita. Assim não expõe banco nenhum, e o arquivo só tem a gold e os marts, agregados com k ≥ 5. A defasagem do arquivo não pesa: ele é regerado a cada carga, que é mensal, e o SLA de frescor é de 35 dias.

## Decisão 3: ETL reverso por push e por estado, com o CSV agendado medido como opção nula

| | **Push por estado** (escolhido) | Pull (o destino consulta o mart) | CSV agendado (opção nula, `--csv`) |
|---|---|---|---|
| Quando | Depois de cada carga mensal (pipeline, Dagster e CI) | Quando a coordenação abre a tela | Depois de cada carga |
| Custo medido | 2 a 4 ms para sincronizar os 22 cursos; reexecutar dá "0 novos, 0 atualizados" | Uma consulta por abertura (0,23 ms) | Menos de 1 s |
| Andamento da coordenação | Na mesma linha, preservado entre ciclos; episódios encerrados guardados (migração 0031) | Sem lugar para gravar: o mart é recriado a cada `dbt build` | Fica fora do arquivo, numa planilha à parte que o CSV seguinte não conhece |
| Curso que sai da fila | Fica, com a data de saída | Some | Some |
| Privilégio mínimo | `coordenacao_academica` grava só status, responsável e plano | Leitura | Quem tem o arquivo altera tudo |
| Destino fora do ar | 4 tentativas (2, 4 e 8 s), depois código 2 e o retry do Dagster. Por estado, nada fica pendente: a execução seguinte que conectar leva o destino ao estado atual | Não se aplica | Não se aplica |

O pull não atende porque a fila precisa **guardar o que a coordenação faz**, e o mart é recriado a cada carga. O CSV basta para **avisar** a coordenação, mas não para **acompanhar** se a intervenção funcionou, que é a pergunta do DEG. Ele continua disponível (`--csv`) para quem só precisa do aviso.

## Consequências

- **A definição de cada métrica tem um lugar só,** e o build quebra se alguém a refizer fora dele. Em troca, uma métrica nova exige macro, linha no registro e testes. Isso é proposital.
- **O painel público não depende de nenhum servidor.** Em troca, mostra o dado da última publicação, e não o do banco naquele instante.
- **A fila é uma tabela operacional com escritor de verdade** (a coordenação). Ela entra na análise de LGPD (`docs/analise_lgpd.md`), porque o nome do responsável é dado pessoal de servidor.

## Gatilhos de revisão

- **Surgir um consumidor que combine métricas e recortes livremente**, como uma ferramenta de BI ou uma API para outras unidades. Aí a camada semântica em ferramenta passa a se pagar, e as macros viram a fonte das métricas dela.
- **Um teste de definição única falhar no CI**, ou uma métrica aparecer em duas telas sem estar no registro. Seria sinal de que a disciplina à mão não está segurando.
- **O painel público passar a ter servidor com acesso ao banco.** A cópia por arquivo deixa de ser necessária, e a leitura direta (0,23 ms) passa a valer.
- **A coordenação não registrar andamento em dois ciclos seguidos.** A fila não estaria sendo usada, e a opção nula (CSV) bastaria.
- **O destino da fila ir para um banco separado** (`ETL_REVERSO_DATABASE_URL`, por exemplo o Supabase). Aí é preciso medir a latência e a taxa de falha do push, que aqui não foram medidas.
- **O Supabase passar de 80% da cota de 500 MB.**

**Estado em 24/11/2026:** nenhum gatilho disparou. A decisão é desta entrega.
