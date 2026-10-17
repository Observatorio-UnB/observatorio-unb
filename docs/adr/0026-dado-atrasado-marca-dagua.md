# ADR 0026: Dado atrasado aceito e registrado pela marca d'água, com reprocessamento só da janela alterada

- **Status:** Aceita
- **Data:** 2026-10-13

## Contexto

O tempo de evento de um vínculo é o período da saída (formatura ou evasão). O tempo de processamento é a publicação do arquivo no portal. Uma saída só entra no arquivo quando é registrada, e a formatura só quando o diploma é registrado. Por isso um semestre continua recebendo vínculos depois de terminar:

| SIGAA publicado em 15/07/2024 | 2023/1 | 2023/2 | 2024/1 |
|---|---|---|---|
| Formaturas | 4.176 | 3.223 | 651 |

O 2024/1 ainda estava sendo registrado quando o arquivo saiu. Uma publicação seguinte traria formaturas desse semestre e, com o registro lançado depois da data, também de semestres anteriores. A gold publica as coortes até 2016 (ADR 0014), e uma saída que chega numa dessas coortes muda um número já publicado. Até aqui a recarga mensal só sobrescrevia, sem registrar o que mudou nem em que período.

Para saber quanto tempo um semestre leva para fechar, o atraso foi medido no SIGRA, que publica o período de saída e a data de registro do diploma. O SIGAA só publica o registro (ADR 0015). Foram 25.485 formados, com o fim nominal do semestre em julho e dezembro, e o do verão em fevereiro:

| Dias do fim do semestre até o registro | Mediana | p90 | p95 | p99 | Mais de 4 meses |
|---|---|---|---|---|---|
| SIGRA | −13 | 19 | 40 | 105 | 0,8% |

## Decisão

- **Marca d'água com 4 meses de tolerância.** A marca d'água de uma carga é o último período cujo fim, somado a 4 meses, não passa da publicação do arquivo de vínculos (`bronze.ingestoes`, data do recurso no CKAN). Até ela, o período é dado como fechado. Os 4 meses cobrem o p99 do SIGRA e são também a janela da regra do ADR 0015, em que o 2º semestre recebe registros até abril. Para o SIGAA de 15/07/2024, a marca é 2024/0, e o 2024/1 fica aberto.
- **Retrato de cada carga.** `src/db/povoar_silver_3nf.py` chama `registrar_carga` (`src/db/dado_atrasado.py`) na mesma transação da carga. Ela grava a marca d'água em `silver.cargas_vinculos` e, em `silver.cargas_vinculos_retrato`, quantos vínculos há por ano de ingresso, desfecho e período de saída. São 549 linhas por carga, só contagens. Ficam na silver, fora do alcance do papel de leitura.
- **Classificação contra a carga anterior.** A view `silver.chegadas_por_carga` (migração 0021) compara cada retrato com o anterior e classifica cada diferença pela marca d'água da carga anterior:
  - `NO_PRAZO`: período depois da marca, ainda aberto;
  - `ATRASADA`: período até a marca, já dado como fechado;
  - `SEM_PERIODO`: vínculo sem período de saída (ativo, cancelado no SIGAA, formado sem diploma registrado).

  `coorte_publicada` marca a mudança em coorte que já estava na gold.
- **O dado atrasado é aceito, e não descartado.** Ao contrário de um painel em streaming, aqui a fonte é a referência. Descartar a chegada atrasada deixaria a gold divergindo do portal para sempre. A carga aceita tudo, e a gold é recalculada inteira, como já era. A chegada atrasada fica registrada, e o log da carga avisa quando ela revisa coorte publicada.
- **A comparação é pela contagem, e não vínculo a vínculo.** O `id_vinculo` é refeito a cada recarga, e nada garante que a fonte mantenha o pseudônimo do discente entre duas publicações. O preço disso: uma correção que move um vínculo de um período para outro aparece como −1 num e +1 no outro, e uma troca de curso dentro da mesma coorte não muda o retrato.
- **Reprocessamento só da janela alterada.** `src/db/exportar_lago.py --janelas-alteradas`, agora a etapa do lago em `rodar_pipeline.sh`, compara cada tabela com a versão no lago, linha a linha e em todas as colunas. Dos vínculos, só os quinquênios que diferem do banco são regravados, com o overwrite com predicado do ADR 0024. Tabela sem mudança não ganha versão nova. A troca de curso que o retrato não vê muda a janela e entra aqui. O objetivo não é velocidade: o export completo e o incremental levam 1,8 s. O ganho é que as outras partições ficam com os mesmos arquivos e o histórico do Delta mostra só a janela que mudou. O `medalhao.yml` segue com o export completo, porque no CI o lago começa vazio.
- **Ids estáveis entre recargas iguais.** Sem `ORDER BY`, o `id_vinculo` seguia a ordem do plano da junção, que mudou entre execuções (por exemplo, depois do `ANALYZE`). A mesma silver ganhava outros ids, e todas as janelas pareciam alteradas. Isso valia também para o `--quinquenio`: a janela reprocessada podia repetir ids das que ficaram no lago. A carga passou a inserir os vínculos na ordem de `silver.discentes_graduacao` (`ORDER BY dg.id`). Depois disso, duas recargas, cada uma precedida de `ANALYZE`, deram os mesmos ids da anterior.

## Demonstração

`src/db/demonstrar_dado_atrasado.py` simula duas publicações sobre a silver real, com 20 vínculos ativos virando formados em cada uma, e desfaz tudo no fim:

| Publicação | Coorte e diploma | Chegada | Gold | Lago |
|---|---|---|---|---|
| No prazo | 2019, agosto de 2024 (2024/1) | `NO_PRAZO` +20 e `SEM_PERIODO` −20 no quinquênio 2015 | nenhum curso revisado (coorte ainda fora da gold) | só a janela 2015 regravada |
| Atrasada | 2012, março de 2023 (2022/2) | `ATRASADA` +20 e `SEM_PERIODO` −20 no quinquênio 2010, coorte publicada | 14 cursos com contagem revisada | só a janela 2010 regravada |

## Consequências

- **No CI, não há carga anterior.** O banco do CI nasce vazio a cada execução: a primeira carga é registrada, mas não há com o que comparar. A comparação acontece onde o banco persiste, como o volume `pgdata` do `docker-compose.yml` ou um banco dedicado. Guardar o retrato no repositório resolveria, mas publicaria contagens abaixo de 5 por célula (ADR 0005).
- **No SIGAA, o atraso do registro fica disfarçado.** O semestre é estimado pela própria data de registro (ADR 0015), então um diploma registrado com meses de atraso cai num período recente e chega como `NO_PRAZO`. `ATRASADA` aparece quando a data de registro é anterior à marca d'água (lançamento retroativo) e nas correções do SIGRA, que publica o período.
- **Os períodos depois da marca são provisórios, e a gold não os marca.** Nas coortes publicadas (até 2016), 99 formaturas estão no 2024/1, ainda aberto. Outros 2.301 cancelamentos e 150 formaturas sem diploma registrado não têm período. Indicar na gold os números com período aberto fica para depois.
- **Vínculo novo no meio do arquivo desloca os ids dos seguintes.** As janelas desses vínculos são regravadas. O resultado continua correto, só menos incremental.
- **Os fatos da gold mudam a cada carga.** `atualizado_em` e `id_fato` são refeitos, então os fatos são sempre regravados no lago. São tabelas de uma centena de linhas.
