-- Mesmo arredondamento de gold.arredondar (migração 0022): em ponto flutuante, com empate para o par,
-- como o numpy.round. O round(numeric) do PostgreSQL arredonda o empate para cima, e 102/320 = 31,875%
-- daria 31,88 aqui e 31,87 na gold. Volta como numeric, o tipo das colunas dos marts.
{% macro arredondar(expressao, casas) -%}
    (round(({{ expressao }})::double precision * power(10::double precision, {{ casas }}))
        / power(10::double precision, {{ casas }}))::numeric
{%- endmacro %}
