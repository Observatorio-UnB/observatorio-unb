# Relatório de Auditoria e Reconciliação do Banco Online (Supabase)

- **Data da Execução:** `2026-11-02T23:55:00.144655+00:00`
- **Veredito Geral:** **APROVADO**

---

## 1. Extensões e Capacidades Analíticas
- **pgvector:** ✅ Instalada (Versão: `0.8.2`)

## 2. Integridade de Esquema e Migrações
- **Total de migrações locais:** `23`
- **Total aplicadas no Supabase:** `23`
- **Migrações pendentes:** `0`
- ✅ Todas as migrações aplicadas deterministicamente.

## 3. Conformidade LGPD e Minimização de Dados
- **Microdados sensíveis expostos:** `0` linhas
- **Veredito de Privacidade:** ✅ Conforme (Zero registros de microdados de alunos)

| Tabela Sensível (Microdado) | Existe no Destino? | Registros no Supabase | Situação |
| :--- | :---: | :---: | :--- |
| `bronze.sigra_discentes` | Sim | `0` | OK |
| `bronze.sigaa_discentes` | Sim | `0` | OK |
| `bronze.sigaa_ativos` | Sim | `0` | OK |
| `bronze.bolsistas_iniciacao_cientifica` | Sim | `0` | OK |
| `silver.discentes` | Sim | `0` | OK |
| `silver.discentes_graduacao` | Sim | `0` | OK |
| `silver.movimentacoes_vinculos` | Sim | `0` | OK |
| `silver.movimentacoes_p2000_2015` | Sim | `0` | OK |
| `silver.movimentacoes_p2016_2020` | Sim | `0` | OK |
| `silver.movimentacoes_p2021_atual` | Sim | `0` | OK |
| `silver.sigaa_ativos` | Sim | `0` | OK |
| `silver.pibic_bolsistas` | Sim | `0` | OK |

## 4. Controle de Acesso e Privilégio Mínimo
- **Papel `observatorio_leitura`:** ✅ Criado
- **Isolamento de esquemas restritos:** ✅ Bronze e Silver bloqueados

| Esquema | Permissão `USAGE` concedida a `observatorio_leitura` | Regra de Negócio |
| :--- | :---: | :--- |
| `gold` | True | Leitura pública autorizada (dados agregados $k \ge 5$) |
| `busca` | True | Leitura pública de documentos vetoriais |
| `bronze` | False | ⛔ Bloqueado (Dado bruto restrito) |
| `silver` | False | ⛔ Bloqueado (Microdados 3NF restritos) |

## 5. Reconciliação de Contagens das Tabelas Analíticas

| Tabela Analítica | Supabase (Remoto) | Banco Local | Status de Reconciliação |
| :--- | :---: | :---: | :---: |
| `gold.retencao_cursos_unb` | `95` | `N/A` | OK |
| `gold.ativos_hoje_cursos_unb` | `95` | `N/A` | OK |
| `gold.pibic_social_unb` | `92` | `N/A` | OK |
| `gold.regras_harmonizacao_canonicas` | `72` | `N/A` | OK |
| `gold.inep_benchmark_cursos_unb` | `96` | `N/A` | OK |
| `gold.relatorios` | `4` | `N/A` | OK |
| `busca.documentos` | `12978` | `N/A` | OK |
| `gold.dim_campus` | `5` | `N/A` | OK |
| `gold.dim_curso` | `118` | `N/A` | OK |
| `gold.dim_tempo` | `34` | `N/A` | OK |
| `gold.dim_perfil_social` | `10` | `N/A` | OK |
| `gold.fato_retencao_curso` | `95` | `N/A` | OK |
| `gold.fato_alunos_ativos` | `95` | `N/A` | OK |
| `gold.fato_pibic_perfil` | `286` | `N/A` | OK |
| `gold.mv_dashboard_executivo` | `94` | `N/A` | OK |

## 6. Recursos e Limites da Infraestrutura
- **Espaço ocupado em disco:** `138 MB` (137.92 MB)
- **Cota do Free Tier:** `500.0 MB` (27.58% utilizado)
- **Conexões ativas no pooler:** `9`
- **Status de capacidade:** ✅ Saudável (abaixo de 90% da cota)

---
*Evidência gerada automaticamente por `src/db/reconciliar_supabase.py`*