# Frescor e SLA da tabela de consumo do painel

**Tabela de consumo:** `gold.mv_dashboard_executivo`, a view que alimenta a Visão Executiva do painel e o ranking de cursos críticos. É o que o DEG lê, no banco local, no Supabase e, pelo export `export/gold.json`, no GitHub Pages.

## O que o SLA promete

| Verificação | Métrica | SLA | Onde é medida |
|:---|:---|:---|:---|
| **Processamento** | Idade da view: `now() - max(gerado_em)`. `gerado_em` é o `now()` do último `REFRESH` | Até **35 dias** | Banco local, Supabase e painel |
| **Fonte** | Para cada arquivo do portal que chega à view, há quanto tempo existe uma publicação que a view ainda não processou | Até **35 dias** depois da publicação | Banco + API do portal (`--fonte`) |

Os arquivos da verificação de fonte são os que chegam à view: SIGRA e SIGAA (vínculos), lista de ativos do SIGAA, estrutura curricular e catálogo de cursos. A publicação de cada um é o `last_modified` do recurso no CKAN, escolhido pela mesma regra da ingestão (`escolher_recurso` em `src/ingestion/ckan_client.py`). Assim o check enxerga o arquivo que o pipeline baixaria.

**Por que 35 dias:** a atualização mensal roda no dia 1 de cada mês (`.github/workflows/atualiza-dados.yml`). Um mês tem até 31 dias, e os 4 dias a mais são o prazo para corrigir uma execução que falhou antes de o painel sair do SLA.

**O que fica de fora:** a idade do dado na origem. O portal publica raramente: na carga de 11/2026, o SIGRA e o SIGAA são de 15/07/2024, a lista de ativos de 17/06/2025 e a estrutura curricular de 20/10/2020. Isso não depende do projeto e não entra no SLA, que cobre só o que o pipeline controla. As limitações que vêm dessa defasagem (evasão recente subestimada, marca d'água) estão no ADR 0014 e no ADR 0026.

## Como é verificado

`src/db/frescor.py` mede as duas verificações e sai com código 1 se alguma passa do SLA:

```bash
python3 src/db/frescor.py                                    # processamento, banco local
python3 src/db/frescor.py --fonte                            # e as publicações do portal
python3 src/db/frescor.py --banco "$SUPABASE_DATABASE_URL" --fonte
```

Saída na carga de 11/2026:

```
OK   processamento (gold.mv_dashboard_executivo): 0.0 de 35 dias (view atualizada em 01/11/2026 20:51 UTC)
OK   fonte (sigra): 0.0 de 35 dias (publicado em 15/07/2024, já processado)
OK   fonte (sigaa): 0.0 de 35 dias (publicado em 15/07/2024, já processado)
OK   fonte (sigaa_ativos): 0.0 de 35 dias (publicado em 17/06/2025, já processado)
OK   fonte (estrutura_curricular): 0.0 de 35 dias (publicado em 20/10/2020, já processado)
OK   fonte (cursos_graduacao): 0.0 de 35 dias (publicado em 24/08/2024, já processado)
SLA de frescor cumprido (6 verificação(ões)).
```

O check roda automaticamente em dois lugares:

| Onde | Quando | O que pega |
|:---|:---|:---|
| `.github/workflows/frescor.yml` | Todo dia, 12:00 UTC, contra o Supabase | Pipeline parado (a view envelhece) e publicação nova do portal que não entrou |
| Passo "Frescor — SLA da view do painel" do Medalhão | A cada execução, logo depois da carga | Quebra do próprio check e publicação mais nova que a carga |

## O que acontece quando o SLA é violado

1. **O workflow falha.** O `frescor.yml` fica vermelho, e o GitHub avisa por e-mail quem acompanha o repositório.
2. **O painel avisa quem lê.** A barra lateral troca a legenda "🟢 Dados atualizados em ..." por um aviso "Fora do SLA de frescor". A idade é calculada na hora em que o painel é aberto, e não no export. Por isso a versão estática do GitHub Pages também mostra quando o export envelheceu.
3. **Correção:** ver por que a atualização mensal não rodou (Actions → Atualização mensal dos dados) e rodá-la manualmente (**Run workflow**). Ela versiona os dados e dispara o Medalhão, que atualiza o Supabase e o Pages.

**Exemplo real:** as duas execuções agendadas da atualização mensal, em 01/10 e 01/11/2026, falharam no passo de versionamento (corrigido no PR #46), e nenhuma delas disparou o Medalhão. A view do Supabase seguiu dentro do SLA só porque o Medalhão também roda a cada push na `main`: a última sincronização foi a do push de 26/10/2026. Sem um push novo nem uma atualização mensal que funcione, ela sai do SLA em 30/11/2026 às 17:53 UTC, e o `frescor.yml` acusa a violação no dia seguinte.

## Testes

- `tests/test_unit_frescor.py`: limites do SLA (35 dias passa, 35 dias e 1 hora viola), publicação já processada não conta, publicação nova pendente dentro e fora do SLA, escolha do mesmo recurso que a ingestão e código de saída.
- `tests/test_banco_frescor.py`: com o banco do pipeline, a view recém-atualizada cumpre o SLA, e a mesma view vista 36 dias depois viola.
