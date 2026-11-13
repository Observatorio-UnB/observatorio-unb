# Benchmark do chat: qwen2.5:7b-instruct

Data: 2026-11-12. 12/16 acertos.

| Resultado | Tempo | SQL | Erros SQL | Pergunta |
|---|---|---|---|---|
| ok | 199s | 1 | 0 | Quantos cursos existem na tabela de retenção? |
| ok | 52s | 1 | 0 | Quais os 5 cursos com maior índice de retenção crítica (IRC)? |
| ok | 21s | 1 | 0 | Quantos cursos têm classificação de retenção CRÍTICA? |
| ok | 22s | 1 | 0 | Qual curso tem a maior taxa de evasão? |
| ok | 33s | 1 | 0 | Qual a taxa de formatura do curso de CIENCIA DA COMPUTACAO? |
| ok | 52s | 2 | 1 | Quantos cursos são do campus FCTE? |
| ok | 23s | 1 | 0 | Qual a média da taxa de evasão entre todos os cursos? |
| ok | 21s | 1 | 0 | Quantos discentes ativos existem hoje, somando todos os cursos? |
| ok | 79s | 3 | 2 | Qual curso tem mais ativos acima do prazo ideal? |
| falha | 24s | 1 | 0 | Quantos planos de iniciação científica existem no total? |
| ok | 29s | 1 | 0 | Qual campus tem mais planos de iniciação científica? |
| falha | 27s | 1 | 0 | Qual o valor total investido em bolsas de iniciação científica, em reais? |
| falha | 319s | 6 | 5 | Em qual curso a desvinculação da UnB mais supera a mediana das outras federais (em pontos percentuais)? |
| ok | 31s | 1 | 0 | Quantos cursos têm mais de 50% dos formados concluindo no tempo ideal? |
| falha | 368s | 2 | 1 | Como é calculado o índice de retenção crítica (IRC)? |
| ok | 139s | 2 | 1 | Liste o nome e a matrícula dos discentes do curso de Ciência da Computação. |
