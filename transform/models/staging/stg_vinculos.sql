-- Um vínculo de graduação por linha. Fica fora o id_discente: nenhuma camada adiante precisa
-- saber de quem é o vínculo.
select
    id_vinculo,
    id_estrutura,
    ano_ingresso,
    tipo_saida_grupo,
    ano_saida,
    periodo_saida_estimado,
    semestres_permanencia_valida,
    fonte
from {{ source('silver', 'movimentacoes_vinculos') }}
