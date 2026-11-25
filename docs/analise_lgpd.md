# Análise de LGPD do que foi construído (E4)

Para cada lugar da plataforma onde há dado de pessoa, esta página diz qual é o dado, sob que base legal é tratado, por quanto tempo fica, como é descartado e quem pode lê-lo. Também mede o risco de **reidentificação por cruzamento** de bases. Ela complementa o [registro de privacidade](registro_privacidade_lgpd.md), gerado a cada pipeline por `src/privacy/lgpd_check.py`, com o k-anonimato dos quase-identificadores; e o [catálogo de ativos da linhagem](catalogo/linhagem.md), que marca cada tabela com registro de pessoa.

> É a análise técnica da Squad sobre a Lei nº 13.709/2018 (LGPD), e não um parecer jurídico. A base legal indicada é a que a Squad entende aplicável a um projeto acadêmico da UnB sobre dados abertos.

## 1. Bases legais usadas

| Base | Artigo | Onde se aplica |
|---|---|---|
| **Estudos por órgão de pesquisa**, garantida, sempre que possível, a anonimização | Art. 7º, IV | Todo o tratamento dos vínculos, alunos e planos de IC. A UnB é órgão de pesquisa (art. 5º, XVIII), e o projeto é uma disciplina dela |
| A mesma base, para **dado sensível** | Art. 11, II, *c* | Raça/cor (dado sensível, art. 5º, II), que vem nos arquivos do SIGRA e do SIGAA |
| **Dado de acesso público**: o tratamento respeita a finalidade, a boa-fé e o interesse público que justificaram a publicação | Art. 7º, § 3º | Os arquivos do portal dados.unb.br, publicados pela própria UnB para prestação de contas |
| **Execução de políticas públicas** pela administração pública | Art. 7º, III, e art. 23 | A fila de intervenção e a lotação das secretarias: o nome de servidor, para a coordenação e o DEG agirem sobre a retenção |
| **Conservação para estudo** por órgão de pesquisa, depois do fim do tratamento, anonimizada sempre que possível | Art. 16, II | O retrato agregado por carga, que é guardado entre as cargas |

Os princípios que guiam as escolhas são finalidade, necessidade e segurança (art. 6º, I, III e VII), e a segurança das tabelas segue o art. 46. Pela **necessidade**, o que não serve à pergunta de gestão não entra: nome, CPF e matrícula são descartados em memória na ingestão e nunca chegam ao disco (ADR 0017 e 0020).

## 2. Inventário: dado, base, retenção, descarte e acesso

| Onde | Dado de pessoa | Base | Retenção | Descarte | Quem lê |
|---|---|---|---|---|---|
| `bronze.sigra_discentes`, `bronze.sigaa_discentes` | Pseudônimo, data de nascimento, sexo, **raça/cor**, cota, curso e saída | Art. 7º, IV, e § 3º; art. 11, II, *c* | Só a última publicação do portal. Cada carga mensal substitui a anterior | `TRUNCATE` + `COPY` numa transação, a cada carga (`src/db/tabelas.py`) | Só o dono do banco |
| `bronze.sigaa_ativos` | Grau, curso e ingresso de cada aluno ativo. Nome, CPF e nacionalidade são descartados em memória | Art. 7º, IV, e § 3º | Última publicação | `TRUNCATE` a cada carga | Só o dono |
| `bronze.bolsistas_iniciacao_cientifica` | Título do plano, ano, bolsa, cota, vigência e unidade. Sem nome, matrícula e orientador | Art. 7º, IV, e § 3º | Última publicação | `TRUNCATE` a cada carga | Só o dono |
| `silver.discentes_graduacao`, `silver.discentes` | Pseudônimo, nascimento, sexo, raça/cor e cota | Art. 7º, IV; art. 11, II, *c* | Recarga mensal | `TRUNCATE` a cada carga | Só o dono |
| `silver.movimentacoes_vinculos` | Vínculo com `id_discente` (pseudônimo) | Art. 7º, IV | Recarga mensal | `TRUNCATE` a cada carga | Dono; `secretaria_campus` só os vínculos dos seus campi e **sem** `id_discente` (migração 0030) |
| `silver.pibic_bolsistas`, `silver.pibic_projetos` | Plano de IC com cota e faixa de renda | Art. 7º, IV | Recarga mensal | `TRUNCATE` a cada carga | Só o dono |
| `dbt_staging`, `dbt_intermediate` | Vínculo por linha, sem `id_discente` | Art. 7º, IV | Nenhuma: são **views**, e não guardam dado | — | Só o dono |
| Lago Delta (`data/lake/`) | Silver 3NF sem `silver.discentes` | Art. 7º, IV | Versões anteriores por **7 dias** (VACUUM, ADR 0024). Fora do repositório (`.gitignore`) | VACUUM; apagar a pasta | Quem tem acesso à máquina ou ao runner |
| Tópicos do Kafka (CDC, opcional) | Eventos dos vínculos, inclusive `id_discente` | Art. 7º, IV | **Indefinida** (`retention.ms=-1`, ADR 0025), enquanto o container existir | `scripts/cdc.sh remover` e recriar o container do Kafka, que não tem volume | Só quem roda o profile `cdc` |
| CI (GitHub Actions) | Bronze e silver no PostgreSQL de serviço do job | Art. 7º, IV | Só o tempo do job | O container é destruído ao fim do job. O artefato `site-data` leva só gold e docs, com 1 dia de retenção | O runner |
| `busca.documentos` (local e Supabase) | Título, ano, curso e campus de cada plano de IC (sem nome) | Art. 7º, IV, e § 3º | Até a próxima vetorização, que remove o que saiu da fonte | Remoção na vetorização | `observatorio_leitura` |
| `operacional.fila_intervencao`, `operacional.fila_intervencao_episodios` | **Nome do responsável** (servidor) e o plano de ação em texto livre | Art. 7º, III; art. 23 | Enquanto a fila existir; os episódios encerrados não têm prazo (**lacuna 2**) | Hoje, nenhum automático | `coordenacao_academica` |
| `acesso.lotacao_campus` | Login do servidor da secretaria e o campus | Art. 7º, III; art. 46 | Enquanto a pessoa estiver lotada | `DELETE` da linha, que revoga o acesso na hora | O próprio usuário, só a sua linha (RLS) |
| Gold, `dbt_marts`, `export/gold.json`, painel e Supabase | **Nenhum**: agregados por curso com k ≥ 5 (ADR 0005). `CHECK` no esquema e auditoria a cada sincronização (ADR 0031) | — | — | — | Público |

## 3. Reidentificação por cruzamento

Duas bases pseudonimizadas podem identificar juntas quem nenhuma identifica sozinha. Os cruzamentos possíveis com o que a plataforma guarda são estes:

| Cruzamento | Risco medido | Por que não vaza |
|---|---|---|
| **Quase-identificadores de uma base só** (curso, nascimento, sexo, raça/cor) | k = 1 em **88,93%** dos registros do SIGRA e **65,63%** do SIGAA (`registro_privacidade_lgpd.md`) | Os quatro só existem na bronze e na silver, que só o dono lê. Nascimento, sexo e raça/cor não passam para a gold |
| **PIBIC × vínculos** (curso, ano e cota do plano contra os alunos do curso naquele ano) | Dos **12.497** planos ligáveis por curso e ano, **120 (1,0%)** ficam com menos de 5 candidatos quando se junta a cota, e **8 (0,1%)** com um candidato só | O cruzamento exige `silver.pibic_bolsistas` e `silver.discentes_graduacao`, que só o dono lê. O que vai a público (`gold.pibic_social_unb`) é agregado com k ≥ 5, e o índice de busca não guarda a cota do plano |
| **UnB × INEP** | Nenhum individual | O INEP entra como agregado por curso (o benchmark), e não por aluno |
| **Painel × portal** (alguém juntar o que publicamos com os arquivos do próprio portal) | Não aumenta o risco | O que publicamos é agregado com k ≥ 5. O risco que existe está nos arquivos que o portal já publica, e não no que a plataforma acrescenta |

A regra que sustenta tudo isso é que **dado individual não sai do banco local**: nem para o Supabase (ADR 0031), nem para o export, nem para o repositório.

## 4. Lacunas encontradas e o que fazer

| # | Lacuna | Risco | Encaminhamento |
|---|---|---|---|
| 1 | **Os tópicos do CDC não têm prazo** (`retention.ms=-1`) e guardam o `id_discente` | Um ambiente de CDC esquecido acumula eventos de vínculo sem limite | O CDC é opcional e só sobe para demonstração. Rodar `scripts/cdc.sh remover` e derrubar o Kafka ao terminar. Se o CDC virar caminho principal (gatilho do ADR 0025), definir a retenção e um volume com prazo |
| 2 | **Os episódios da fila guardam o nome do responsável para sempre** | Nome de servidor guardado além da finalidade | Regra proposta: depois de 2 anos do fim do episódio, trocar o nome pela função ("coordenação do curso"). Ainda não implementada |
| 3 | **O plano de ação é texto livre** | A coordenação pode escrever ali o nome ou a situação de um aluno | Orientação na tela e no treinamento: o plano descreve a ação do curso, e não pessoas. Revisar se aparecer dado de aluno |
| 4 | **Título de plano de IC no índice de busca** | Com curso e ano, um título pode levar ao trabalho publicado no RIUnB | É dado que o portal já publica. A plataforma não acrescenta nome nem cota. Fica registrado |
