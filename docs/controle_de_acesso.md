# Controle de acesso por linha e por coluna (E4)

A E4 pede controle de acesso demonstrado em pelo menos um recorte de linha ou de coluna, com privilégio mínimo. Este projeto aplica os dois recortes na mesma tabela: `silver.movimentacoes_vinculos`, a do vínculo individual.

## O problema

Até a E3 havia dois níveis ([ADR 0010](adr/0010-controle-de-acesso-leitura.md)):

| Papel | Lê | Para quem |
|---|---|---|
| `observatorio_leitura` | gold, busca, `dbt_marts` (agregados, k ≥ 5) | painel, consultas analíticas |
| dono do banco | tudo | pipeline |

Quem precisa do **vínculo individual** para trabalhar não tinha papel próprio. É o caso da secretaria acadêmica de um campus, que acompanha os alunos dos próprios cursos. A única saída era usar o dono do banco, que vê os quatro campi e o `id_discente`, a chave que liga o vínculo a nascimento, sexo e raça/cor em `silver.discentes`.

## A solução: papel `secretaria_campus` ([migração 0030](../db/migrations/0030_acesso_por_campus_linha_e_coluna.sql))

| Recorte | Como | Efeito |
|---|---|---|
| **Linha** (RLS) | Política `vinculos_do_campus_lotado` em `silver.movimentacoes_vinculos` | O usuário vê só os vínculos de cursos dos campi em que está lotado (`acesso.lotacao_campus`). Sem lotação, não vê nenhuma linha. |
| **Coluna** | `GRANT SELECT (...)` com todas as colunas menos `id_discente` | O vínculo não se liga à pessoa. `SELECT *` é negado. |
| Tabelas vizinhas | Sem grant em `silver.discentes`, bronze, gold, partições e escrita | Não há atalho para o dado pessoal nem para fugir da política pela partição. |
| Lotação | RLS também em `acesso.lotacao_campus` (`usuario = current_user`) | O usuário não descobre quem mais tem acesso a quê. |

O pipeline, o dbt, o export do lago e o CDC (Debezium) usam o dono da tabela, que não passa pela RLS (sem `FORCE ROW LEVEL SECURITY`). A carga não muda, e o teste `test_09` confere isso.

### Conceder e revogar

```sql
CREATE ROLE maria LOGIN PASSWORD '...' IN ROLE secretaria_campus;
INSERT INTO acesso.lotacao_campus (usuario, campus)
VALUES ('maria', 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)');

-- Revogar o acesso a um campus vale na hora, sem mexer em GRANT:
DELETE FROM acesso.lotacao_campus WHERE usuario = 'maria' AND campus = '...';
```

## Demonstração

`python3 src/db/demonstrar_controle_de_acesso.py` cria três usuários de exemplo numa transação, consulta como cada um e desfaz tudo no fim. Saída na carga de 24/11/2026:

```
Dono do banco: 152.680 vínculos em 4 campi.

| Usuário | Lotação | Vínculos vistos | Esperado (dono, mesmos campi) |
|---|---|---|---|
| demo_secretaria_fcte | FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE) | 8620 | 8620 |
| demo_secretaria_fcts_fup | FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS), FACULDADE DE PLANALTINA (FUP) | 18096 | 18096 |
| demo_sem_lotacao | (nenhuma) | 0 | 0 |

| Tentativa (como demo_secretaria_fcte) | Resultado |
|---|---|
| coluna id_discente | negada |
| partição direta | negada |
| silver.discentes | negada |
| escrita no vínculo | negada |
| gold sem papel de leitura | negada |
| demais colunas do vínculo | permitidas |

Contagem dos vínculos da FCTE, mediana de 15: 0.4 ms pela política (RLS) contra 0.6 ms com o filtro escrito à mão pelo dono.

Transação desfeita: papéis e lotação de exemplo removidos.
```

## O custo da política, e o ajuste que ela pediu

A primeira versão da política usava `id_curso IN (SELECT ...)`. O PostgreSQL a executava como um subplano com hash, testado linha a linha nas 152 mil linhas das quatro partições. A contagem da FCTE levava **7,9 ms pela política, contra 0,8 ms** com o mesmo filtro escrito à mão.

Com `id_curso = ANY (ARRAY(SELECT ...))`, a lista de cursos do usuário é calculada uma vez (`InitPlan`) e vira condição do índice `(id_curso, ano_ingresso)` de cada partição. A política passou a custar o mesmo que o filtro à mão (**0,4 a 0,6 ms**). O `test_10` falha se o plano voltar ao subplano com hash.

## Testes

`tests/test_banco_controle_de_acesso.py` tem 10 testes:

- recorte de linha: um campus, dois campi, nenhum, e revogação que vale na hora;
- recorte de coluna;
- partições, `silver.discentes` e bronze negados;
- nenhuma escrita;
- lotação dos outros invisível;
- dono do banco intacto;
- política usando o índice.
