-- Valor da coluna dentro de [minimo, maximo]; nulo passa (o not_null é outro teste).
{% test entre(model, column_name, minimo, maximo) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} not between {{ minimo }} and {{ maximo }}
{% endtest %}
