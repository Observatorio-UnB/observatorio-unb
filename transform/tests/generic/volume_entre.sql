-- Volume: o modelo tem de ter entre `minimo` e `maximo` linhas. Pega a carga parcial (arquivo
-- truncado, partição que não veio) e a duplicação em massa, que nenhum teste de linha vê.
{% test volume_entre(model, minimo, maximo) %}
select count(*) as linhas
from {{ model }}
having count(*) not between {{ minimo }} and {{ maximo }}
{% endtest %}
