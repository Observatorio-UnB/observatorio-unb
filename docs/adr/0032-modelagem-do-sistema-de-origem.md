# 0032 — Sistema de origem em 3NF, recarregado por inteiro, com o tempo de evento em cada vínculo

- **Status:** aceito
- **Data:** 2026-11-24 (registra a modelagem adotada na migração 0011, na semana 06, que não tinha ADR próprio)
- **Decisores:** Squad Observatório UnB (redação: Leandro de Almeida Oliveira; revisão no PR #85: vcpVitor)

## Contexto

A E1 pede um sistema de origem OLTP que poderia estar em produção, e um ADR sobre a modelagem dele. O domínio são os vínculos de graduação da UnB (SIGRA e SIGAA, no portal dados.unb.br). A pergunta de gestão é: *"Em quais cursos a taxa de retenção e atraso na integralização curricular é mais crítica, demandando intervenções institucionais prioritárias?"*

A carga, caracterizada em [caracterizacao_da_carga.md](../caracterizacao_da_carga.md), é esta:
- 152.680 vínculos, 125.154 alunos, 158 ofertas de curso e 112 matrizes;
- crescimento de 10 a 13 mil vínculos por ano;
- **um escritor só** (o pipeline), com recarga mensal em 3,4 s;
- leitura rara e agregada por curso e coorte, com o SLA de frescor de 35 dias.

Três perguntas definem a modelagem: até onde normalizar, se a origem preserva histórico ou sobrescreve, e que carimbo de tempo cada tabela guarda.

## Alternativas consideradas

### A. Opção nula — continuar como está

A tabela larga, como a silver era antes da 3NF: um vínculo por linha, com tudo junto (`silver.discentes_graduacao`, que continua existindo como etapa da carga). O curso é texto, sem chave para o catálogo.

### B. 3NF

`cursos`, `estruturas_curriculares`, `discentes` e `movimentacoes_vinculos`, com chaves e restrições, e cada fato num lugar só ([prova da 3NF](../arquitetura/01_PROVA_MATEMATICA_NORMALIZACAO_3NF.md)).

### C. Insert-only (uma cópia por publicação)

A 3NF, mais uma chave de publicação em cada linha, guardando todas as fotos da fonte em vez de sobrescrever.

## Medição

| Alternativa | Tamanho | Integridade | Anomalias | Histórico | Leitura típica (detalhe de um curso, coortes de 2010 a 2016) |
|---|---|---|---|---|---|
| A — opção nula (tabela larga) | 66 MB | Nenhuma entre vínculo e curso: o curso é texto | Nascimento, sexo e raça/cor repetidos em cada vínculo dos 14.005 alunos (11%) que têm mais de um. O prazo da matriz se repete em cada vínculo do curso | Sobrescreve | Sem junção |
| **B — 3NF** | **46 MB** (discentes + vínculos), 30% menos | 4 FK, 4 PK, 3 UNIQUE e 12 CHECK; 26 colunas NOT NULL | Cada fato num lugar só | Sobrescreve | Uma junção, 0,42 ms (`docs/explain/`) |
| C — insert-only | 46 MB por publicação guardada | Igual à 3NF | Igual à 3NF | Diferença entre fotos, porque a fonte não publica a trajetória do aluno | Uma junção a mais, filtrando a publicação |

Como reproduzir (banco do `docker compose`, depois do pipeline):

```sql
-- Tamanho: tabela larga contra 3NF (discentes + partições dos vínculos)
SELECT pg_size_pretty(pg_total_relation_size('silver.discentes_graduacao')) AS larga,
       pg_size_pretty(pg_total_relation_size('silver.discentes')
         + (SELECT sum(pg_total_relation_size(inhrelid)) FROM pg_inherits
            WHERE inhparent = 'silver.movimentacoes_vinculos'::regclass)::bigint) AS tres_fn;

-- Alunos com mais de um vínculo (onde a tabela larga repete os dados pessoais)
SELECT count(*) FILTER (WHERE n > 1)
FROM (SELECT id_discente, count(*) n FROM silver.movimentacoes_vinculos GROUP BY 1) x;

-- Restrições do OLTP, por tipo (c = CHECK, f = FK, p = PK, u = UNIQUE)
SELECT contype, count(*) FROM pg_constraint
WHERE conrelid IN ('silver.cursos'::regclass, 'silver.estruturas_curriculares'::regclass,
                   'silver.discentes'::regclass, 'silver.movimentacoes_vinculos'::regclass)
GROUP BY 1;
```

O tempo da leitura típica está em `docs/explain/distribuicao_formatura_por_curso.sql`, com o plano versionado ao lado.

## Decisão

Escolhemos **a 3NF (B), recarregada por inteiro a cada carga**:

- **3NF no OLTP.** Os vínculos ficam em `silver.movimentacoes_vinculos`, com chave estrangeira para a matriz (`estruturas_curriculares`), para o curso (`cursos`) e para o aluno (`discentes`). O que é do aluno (nascimento, sexo e raça/cor) fica uma vez em `silver.discentes`, separado do vínculo. Assim, os dados pessoais ficam numa tabela só, que os demais papéis não leem (ADR 0010).
- **A desnormalização só onde se paga, e fora do OLTP:**
  - na tabela larga `silver.discentes_graduacao`, que é etapa da carga e não é lida por ninguém depois;
  - na gold e nos marts (estrela, ADR 0030), lidos pelo painel.

  No OLTP há uma redundância deliberada: o vínculo guarda `id_curso` além de `id_estrutura`, embora a matriz já tenha o curso. É a coluna do índice `(id_curso, ano_ingresso)`, e evita a junção com a matriz em filtros por curso. Conferido: 0 de 152.680 vínculos divergem da sua matriz.
- **A origem sobrescreve, e não é insert-only.** A cada carga mensal, a 3NF é substituída pelo arquivo mais recente (`TRUNCATE` + `INSERT ... SELECT` numa transação). A fonte só publica o estado atual de cada vínculo, e a pergunta de gestão se responde com o desfecho de cada vínculo, que está na foto atual. Os detalhes, inclusive o que se pode e o que não se pode perguntar, estão em [historico_da_origem.md](../historico_da_origem.md).
- **O histórico que importa é guardado à parte, e não no OLTP:**
  - contagens por carga, insert-only (`silver.cargas_vinculos`, ADR 0026), para o dado atrasado;
  - a SCD 2 dos atributos do curso (ADR 0028).
- **Carimbos de tempo:**
  - o **tempo de evento** fica no próprio vínculo (`ano_ingresso`, `ano_saida`, `semestre_saida`) e é a base de todas as métricas;
  - a **publicação na fonte** fica em `silver.cargas_vinculos.publicada_em`;
  - a **ingestão**, em `bronze.ingestoes.baixado_em`;
  - o **processamento**, em `_carregado_em` e no `gerado_em` da view do painel, que é a base do SLA.

  Nenhuma métrica usa o tempo de processamento como se fosse evento.
- **Particionamento por ano de ingresso** (2000–2015, 2016–2020, 2021–atual e default; criadas na migração 0011, com as futuras provisionadas pela 0019). É o filtro de toda consulta por coorte e o que o crescimento anual preenche.

## Consequências

**O que ganhamos:**

- O banco recusa vínculo sem curso, sem matriz, com desfecho fora do domínio ou com permanência fora de 1 a 35 semestres. A qualidade do dado é barrada na carga, e não descoberta na E3.
- 30% menos espaço que a tabela larga, e os dados pessoais numa tabela só, fora do alcance dos papéis de leitura.
- A recarga inteira é simples e idempotente: rodar duas vezes dá o mesmo banco.

**O que perdemos:**

- A situação de um vínculo numa data passada se perde a cada carga. Não dá para perguntar quantos alunos estavam trancados em 2019, nem quais vínculos mudaram entre duas publicações.
- Não há como reproduzir pelo banco o ranking de um mês anterior: sobram só as contagens por carga e, por 7 dias, a versão anterior no lago.
- Uma junção a mais em cada leitura por curso. Ela custa pouco (0,42 ms no detalhe de um curso), mas existe; a tabela larga não teria.

**O que se torna irreversível:**

O histórico das cargas passadas. Como a origem sobrescreve, o que não foi guardado no retrato por carga não volta. Passar a insert-only (C) só guarda as publicações dali em diante, e as anteriores estão perdidas.

## Gatilho de revisão

- **A pergunta de gestão passar a exigir trajetória:** por exemplo, quantos alunos estavam trancados em cada semestre, ou quem mudou de situação entre publicações. Aí a origem precisa ficar insert-only, guardando cada publicação com a sua data na bronze e uma chave de publicação na 3NF.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A pergunta da E1 segue respondida pelo desfecho de cada vínculo.
- **Surgir um escritor além do pipeline:** por exemplo, uma secretaria lançando correções. A recarga inteira apagaria essas correções. A origem passaria a receber escrita linha a linha, e o CDC (ADR 0025) viraria o caminho principal.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** A fila de intervenção da E4 tem escritor próprio (a coordenação), mas fica no esquema `operacional`, fora do OLTP; o `secretaria_campus` só lê.
- **A recarga da Silver 3NF passar de 5 minutos** (hoje 3,4 s), por exemplo ao juntar a pós-graduação ou outras universidades. Aí vale a carga incremental.
  - *Estado no semestre (até 24/11/2026):* **Não disparou — decisão mantida.** Mediana de 3,4 s em 3 execuções (`caracterizacao_da_carga.md`).
- **A redundância `id_curso` divergir da matriz em pelo menos 1 vínculo** numa carga. Se acontecer, o `id_curso` sai do vínculo, ou vira restrição verificada.
  - *Estado no semestre (até 24/11/2026):* **Não disparou.** 0 de 152.680.
