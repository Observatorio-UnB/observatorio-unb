-- Camada semântica: a fórmula de cada métrica, num lugar só.
--
-- Todo modelo que publica uma métrica (int_metricas_curso, metricas_por_recorte) a calcula por estas
-- macros, a partir das bases aditivas de int_bases_curso (contagens e somas). Nenhum modelo, nem o
-- painel, nem o ETL reverso, escreve a fórmula de novo. A definição de negócio, a unidade, os recortes
-- válidos e a versão de cada métrica estão em seeds/metricas_definicoes.csv; o teste
-- metricas_registro_completo acusa métrica publicada sem definição, e definição sem métrica.
--
-- Mudar uma fórmula aqui exige subir a versão da métrica no registro (e o ADR que a sustenta).
--
-- As razões seguem a ordem de operações e o arredondamento de gold.atualizar_gold (migração 0022):
-- ponto flutuante, vezes 100, e a macro arredondar. É o que deixa o fato do dbt reconciliar com a
-- gold também nos empates (tests/reconcilia_fato_retencao_com_a_gold.sql).

{% macro metrica_taxa_formatura_pct(formados, ingressantes) -%}
    {{ arredondar(formados ~ "::double precision / nullif(" ~ ingressantes ~ ", 0) * 100", 2) }}
{%- endmacro %}

{% macro metrica_taxa_evasao_pct(evadidos, ingressantes) -%}
    {{ arredondar(evadidos ~ "::double precision / nullif(" ~ ingressantes ~ ", 0) * 100", 2) }}
{%- endmacro %}

-- Só sobre formados com permanência calculável. Sem nenhum, 0 (como na gold).
{% macro metrica_formados_tempo_ideal_pct(formados_no_ideal, formados_com_prazo) -%}
    case when {{ formados_com_prazo }} > 0
         then {{ arredondar(formados_no_ideal ~ "::double precision / " ~ formados_com_prazo ~ " * 100", 2) }}
         else 0 end
{%- endmacro %}

-- Média, entre os formados com permanência e prazo ideal conhecidos, de (permanência - prazo ideal
-- da matriz). soma / contagem em numeric é a mesma conta do avg() do PostgreSQL.
{% macro metrica_atraso_medio_semestres(soma_atraso, formados_com_atraso) -%}
    {{ arredondar(soma_atraso ~ "::numeric / nullif(" ~ formados_com_atraso ~ ", 0)", 2) }}
{%- endmacro %}

-- Média da permanência dos formados com permanência calculável.
{% macro metrica_tempo_medio_formatura_semestres(soma_permanencia, formados_com_prazo) -%}
    {{ arredondar(soma_permanencia ~ "::numeric / nullif(" ~ formados_com_prazo ~ ", 0)", 2) }}
{%- endmacro %}

-- Prazo ideal médio dos mesmos formados do atraso: tempo médio - prazo ideal médio = atraso médio.
{% macro metrica_prazo_ideal_medio_semestres(soma_prazo_ideal, formados_com_atraso) -%}
    {{ arredondar(soma_prazo_ideal ~ "::numeric / nullif(" ~ formados_com_atraso ~ ", 0)", 2) }}
{%- endmacro %}
