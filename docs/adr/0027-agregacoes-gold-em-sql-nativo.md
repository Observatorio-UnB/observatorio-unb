# ADR 0027: Agregações da Gold em SQL nativo no PostgreSQL, sem Pandas nem PySpark

- **Status:** Aceita
- **Data:** 2026-10-29

## Contexto

`src/pipeline/build_gold.py` lia a Silver para o Pandas, agregava em memória (retenção, evasão, IRC, ativos, benchmark INEP, PIBIC) e gravava a Gold de volta. A regra de retenção existia duas vezes: no Pandas e em `SQL_FATO_RETENCAO`, o port para o Star Schema (`src/db/povoar_dimensional.py`), com tolerâncias de 0,01 e 0,1 só para o teste de reconciliação passar.

Foi avaliado também trocar o Pandas pelo PySpark.

## Decisão

- **SQL nativo, sem PySpark.** O volume é de cerca de 150 mil vínculos e 95 cursos na Gold; o Pandas recalculava tudo em segundos. O Spark traria JVM, imagem maior e CI mais lento, e a regra continuaria fora do banco e duplicada com o SQL. Só valeria com ordem de grandeza maior de linhas.
- **A regra mora no banco** (migração 0022). `gold.atualizar_gold(anos_maturacao, cursos_tronco, min_matriculas_inep, valor_bolsa_ic)` chama uma procedure por tabela: `atualizar_regras`, `atualizar_ativos_hoje`, `atualizar_retencao`, `atualizar_inep_benchmark`, `atualizar_pibic_social` e os relatórios JSON. Tudo na transação de quem chama: a Gold é trocada inteira ou não é trocada.
- **Views auxiliares em `silver`** (`v_vinculo_estrutura`, `v_catalogo_curso`, `v_area_curso`, `v_oferta_curso`, `v_curso_misto`), porque `v_vinculo_estrutura` expõe vínculo individual e o papel `observatorio_leitura` não lê a silver. As tabelas da Gold continuam físicas, então painel, sincronização com o Supabase e papel de leitura não mudam.
- **O Python só semeia e dispara.** `build_gold.py` mantém o que é dado (`CANONICAL_RULES_METADATA`, `EXCLUDED_GENERIC_COURSES`, limiares), grava `gold.regras_harmonizacao_canonicas` e executa o `CALL`. O Star Schema passa a copiar `gold.retencao_cursos_unb` em vez de recalcular.
- **Paridade exata, não aproximada.** O arredondamento usa `gold.arredondar`, em ponto flutuante com empate para o par (`numpy.round`). O `round(numeric)` do PostgreSQL arredonda o empate para cima e diverge do Pandas em médias como 8,125. Os primeiros atributos de cada curso saem de `array_agg(... ORDER BY ...)`, que reproduz o `first()` do Pandas (primeiro não nulo) e depende da coluna `_ordem` da Silver.

## Verificação

Antes de remover o Pandas, as cinco tabelas e os quatro relatórios JSON da Gold foram gravados como referência e comparados com `EXCEPT` e `=` contra a saída do SQL, na mesma Silver: zero linhas diferentes (95 cursos de retenção, 95 de ativos, 96 do benchmark, 92 do PIBIC, 72 regras). `tests/test_gold_sql.py` mantém a comparação com um cálculo independente em Pandas, escrito no teste, e confere que regravar dá o mesmo resultado.

Tempo: a Gold inteira recalcula em cerca de 4 s no banco local, contra 5 a 6 s do Pandas. Não houve ganho de desempenho; o ganho é uma regra só, no banco.

## Consequências

- Mudar uma regra da Gold exige migração nova (as migrações aplicadas são imutáveis, ADR 0009), e não editar a 0022.
- `CANONICAL_RULES_METADATA` e `EXCLUDED_GENERIC_COURSES` seguem em Python, porque são dado versionado e outros módulos os importam. O banco os recebe como parâmetro e como tabela.
- Os testes puros dos helpers do Pandas viraram testes das funções e views em SQL.
- Com a Silver vazia, a Gold anterior é mantida, como antes.
- `transform_silver.py`, a ingestão, a auditoria e o painel continuam em Pandas; este ADR trata só da Gold.
