# 0033 — Camada semântica feita à mão no dbt, painel público por arquivo e ETL reverso por push

- **Status:** aceito
- **Data:** 2026-11-24
- **Decisores:** Squad Observatório UnB: Felipe de Sousa Coelho, Joao Victor Marques Reis de Miranda, Leandro de Almeida Oliveira, Murilo Perazzo Barbosa Souto, Thales Germano Vargas Lima e Vitor Carvalho Pereira (redação: Leandro de Almeida Oliveira)

## Contexto

A E4 pede o dado disponibilizado de duas formas: o painel e uma camada semântica com a definição de cada métrica num lugar só. Ela também pede que uma métrica tratada volte a um sistema onde alguém age. Os consumidores são três:

- o **painel público**, no GitHub Pages, que roda no navegador (stlite) e não tem acesso ao banco;
- o **painel local e o Supabase**, que leem a gold e os marts pelo papel `observatorio_leitura`;
- a **fila de intervenção** (`operacional.fila_intervencao`), operada pela coordenação de curso e acompanhada pelo DEG.

O dado muda uma vez por mês, e a fonte publica no máximo uma vez por ano (ver [caracterização da carga](../caracterizacao_da_carga.md)). O volume é pequeno: o ranking tem 94 cursos, os recortes 20 linhas, e a fila 22 cursos.

## Alternativas consideradas

Três escolhas, cada uma com a opção nula.

### 1. Onde mora a definição de cada métrica

- **A. Opção nula — continuar como está:** cada tela calcula a própria métrica, como o painel fazia até a E3.
- **B. Ferramenta (dbt Semantic Layer / MetricFlow):** a métrica é definida em YAML de `metrics` e calculada pelo motor na hora da consulta, servida pela API do Semantic Layer (dbt Cloud) ou pelo `mf` local.
- **C. À mão no dbt:** uma macro por métrica (`transform/macros/metricas.sql`), usada por todo modelo que publica a métrica; a definição versionada num seed (`transform/seeds/metricas_definicoes.csv`); tabelas prontas para os consumidores (`painel_cursos_criticos`, `metricas_por_recorte`).

### 2. Por onde cada consumidor lê

- **A. Opção nula — continuar como está:** ler direto do banco (warehouse).
- **B. Cópia por arquivo:** `export/gold.json`, regerado a cada carga.
- **C. Banco gerenciado (Supabase):** a gold sincronizada num banco na nuvem.
- **D. Federação de consultas:** não se aplica, porque não há uma segunda base para federar. O INEP é ingerido na bronze.

### 3. Como a métrica volta para quem age (ETL reverso)

- **A. Opção nula — CSV agendado** (`--csv`): o mesmo conteúdo da fila, num arquivo, depois de cada carga.
- **B. Push por estado:** depois de cada carga, o ETL leva a fila do destino ao estado da origem.
- **C. Pull:** o destino consulta o mart quando a coordenação abre a tela.

## Medição

Carga de 24/11/2026, num banco montado do zero, mediana de 15 execuções.

**1. Definição da métrica.** A opção nula foi medida no próprio painel, antes da E4. Ele mostrava a mesma métrica de jeitos diferentes:

| Divergência encontrada | Valor numa tela | Valor pela definição | Diferença |
|---|---|---|---|
| Evasão do turno "DIURNO E NOTURNO": média das taxas contra razão das somas | 47,56% | 44,68% | +2,88 p.p. |
| Ingressantes da UnB, com o curso-tronco contra sem | 68.339 | 67.063 | +1.276 |
| % no prazo ideal: segunda implementação em Python | 50,42% | 50,43% | 0,01 p.p. |

Na alternativa C, o tamanho é de 6 macros, 1 seed com 12 métricas e 1 mart com 20 linhas. A alternativa B não foi medida: o painel público não consulta uma API em tempo de execução e teria de pré-calcular as mesmas tabelas de qualquer jeito.

**2. Leitura.**

| Alternativa | Medido | Latência do dado | Custo | Acoplamento |
|---|---|---|---|---|
| A — banco (opção nula) | Ranking em 0,23 ms; recortes em 0,11 ms; snapshot inteiro do painel em 44 ms | Imediata | O banco no ar | Ao esquema e ao papel de leitura |
| B — arquivo (`export/gold.json`) | 1.034 KB; gerado em 50 ms; lido pelo painel em 4 ms | A do último export (a cada push na `main` e no agendamento mensal) | Nenhum serviço: GitHub Pages | Só ao formato do JSON |
| C — Supabase | Gold + busca: 138 MB, 27,6% da cota de 500 MB (ADR 0031). Latência de rede não medida daqui | A da sincronização incremental | Plano gratuito | Ao esquema da gold |

**3. ETL reverso.**

| Alternativa | Custo medido | Andamento da coordenação | Curso que sai da fila | Privilégio mínimo | Destino fora do ar |
|---|---|---|---|---|---|
| A — CSV agendado (opção nula) | Menos de 1 s | Fica fora do arquivo, numa planilha à parte que o CSV seguinte não conhece | Some | Quem tem o arquivo altera tudo | Não se aplica |
| **B — push por estado** | **2 a 4 ms** para os 22 cursos; reexecutar dá "0 novos, 0 atualizados" | Na mesma linha, preservado entre ciclos; episódios encerrados guardados (migração 0031) | Fica, com a data de saída | `coordenacao_academica` grava só status, responsável e plano | 4 tentativas (2, 4 e 8 s), depois código 2 e o retry do Dagster; nada fica pendente |
| C — pull | Uma consulta por abertura (0,23 ms) | Sem lugar para gravar: o mart é recriado a cada `dbt build` | Some | Leitura | Não se aplica |

Como reproduzir:

```bash
bash scripts/dbt.sh build --full-refresh
python3 src/etl_reverso/fila_intervencao.py           # push: "22 novos"; de novo: "0 novos, 0 atualizados"
python3 src/etl_reverso/fila_intervencao.py --csv export/fila_intervencao.csv   # opção nula
python3 src/db/exportar_gold.py                       # cópia por arquivo
python3 -m unittest tests/test_banco_etl_reverso.py   # mesmo número no painel, na fila e nas abas da gold
```

## Decisão

Escolhemos:

1. **A camada semântica feita à mão no dbt (1C).** A ferramenta (1B) só se paga quando há consumidores fazendo consultas ad hoc que combinam métricas e recortes livremente. Aqui os consumidores leem um conjunto fixo de recortes, e um deles nem tem banco. O risco da solução à mão, que é divergir, é coberto por testes que **falham o build**:
   - `metricas_registro_completo`: métrica publicada sem definição, ou o contrário;
   - `metricas_recortes_fecham_com_o_painel`: os recortes somam o mesmo que o ranking;
   - `TestMesmoNumero`: as abas da gold, o ranking e a fila mostram o mesmo número curso a curso.

   Ver `docs/camada_semantica_e_etl_reverso.md`.
2. **Cada consumidor lê pelo caminho mais barato que atende a ele:**
   - o **painel público** lê a **cópia por arquivo (2B)**. Ele roda no navegador de quem visita, então não expõe banco nenhum, e o arquivo só tem a gold e os marts, agregados com k ≥ 5. A defasagem não pesa: o arquivo é regerado a cada carga, que é mensal, e o SLA de frescor é de 35 dias;
   - o **painel local** e o ETL reverso leem o **banco (2A)**;
   - as consultas SQL de fora usam o **Supabase (2C)**.
3. **O ETL reverso por push e por estado (3B).** O pull (3C) não atende porque a fila precisa **guardar o que a coordenação faz**, e o mart é recriado a cada carga. O CSV (3A) basta para **avisar** a coordenação, mas não para **acompanhar** se a intervenção funcionou, que é a pergunta do DEG. Ele continua disponível (`--csv`) para quem só precisa do aviso.

## Consequências

**O que ganhamos:**

- A definição de cada métrica tem um lugar só, e o build quebra se alguém a refizer fora dele. As três divergências da tabela acima viraram testes.
- O painel público não depende de nenhum servidor, nem expõe o banco.
- A fila guarda o andamento da coordenação entre ciclos, e o DEG consegue ver se os cursos com plano saíram da fila.

**O que perdemos:**

- Uma métrica nova exige macro, linha no registro e testes, e não só uma fórmula numa tela. É proposital, mas é mais trabalho.
- Sem a ferramenta (1B), não há consulta ad hoc de métrica por recorte livre: só os recortes pré-calculados (UnB, campus, grau, área, turno).
- O painel público mostra o dado da última publicação, e não o do banco naquele instante.
- A fila é uma tabela operacional com escritor de verdade, a coordenação, e o nome do responsável é dado pessoal de servidor. Ela entra na análise de LGPD (`docs/analise_lgpd.md`).

**O que se torna irreversível:**

O andamento que a coordenação registra na fila e nos episódios. Ele só existe lá, e não sai do pipeline nem pode ser regerado a partir da fonte. Por isso a fila não pode ser recriada como os marts: apagar a tabela perderia o histórico das intervenções. O resto (macros, marts, export) é regerado a cada carga.

## Gatilho de revisão

- **Surgir um consumidor que combine métricas e recortes livremente**, como uma ferramenta de BI ou uma API para outras unidades. Aí a camada semântica em ferramenta (1B) passa a se pagar, e as macros viram a fonte das métricas dela.
- **Um teste de definição única falhar no CI**, ou uma métrica aparecer em duas telas sem estar no registro. Seria sinal de que a disciplina à mão não está segurando.
- **O painel público passar a ter servidor com acesso ao banco.** A cópia por arquivo deixa de ser necessária, e a leitura direta (0,23 ms) passa a valer.
- **A coordenação não registrar andamento em dois ciclos seguidos.** A fila não estaria sendo usada, e a opção nula (CSV) bastaria.
- **O destino da fila ir para um banco separado** (`ETL_REVERSO_DATABASE_URL`, por exemplo o Supabase). Aí é preciso medir a latência e a taxa de falha do push, que aqui não foram medidas.
- **O Supabase passar de 80% da cota de 500 MB** (hoje 27,6%).

**Estado em 24/11/2026:** nenhum gatilho disparou. A decisão é desta entrega.
