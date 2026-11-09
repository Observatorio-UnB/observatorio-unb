-- Dimensão de cursos, SCD tipo 2 (ADR 0028): uma linha por versão dos atributos de classificação de
-- um curso canônico. O histórico vem do snapshot snap_atributos_curso; esta tabela só o apresenta.
--
-- Vigência: a primeira versão de cada curso vale desde 21/04/1962 (fundação da UnB), como na
-- gold.dim_curso. Não existe histórico anterior ao início do rastreamento, e a data fixa faz a
-- primeira versão ter a mesma chave em qualquer banco. As versões seguintes começam na execução do
-- dbt que observou a mudança. A versão atual tem is_atual e vigente_ate nulo.
--
-- Chave substituta: hash do nome canônico com o início da vigência. Estável entre execuções: a
-- reconstrução dos marts (--full-refresh) gera as mesmas chaves a partir do mesmo snapshot.
with versoes as (
    select
        s.nome_curso,
        s.id_curso_origem,
        s.grau_academico,
        s.categoria_grau,
        s.area_conhecimento,
        s.departamento,
        s.is_tronco_abi,
        case
            when row_number() over (partition by s.nome_curso order by s.vigente_de) = 1
                then timestamp '1962-04-21 00:00:00'
            else s.vigente_de
        end as vigente_de,
        s.vigente_ate
    from {{ ref('snap_atributos_curso') }} s
)

select
    md5(v.nome_curso || '|' || to_char(v.vigente_de, 'YYYY-MM-DD HH24:MI:SS.US')) as sk_curso,
    v.nome_curso,
    -- Tipo 1: vale o ponteiro atual, em todas as versões. Curso que sumiu da origem fica com o último.
    coalesce(atual.id_curso_origem, v.id_curso_origem) as id_curso_origem,
    v.grau_academico,
    v.categoria_grau,
    v.area_conhecimento,
    v.departamento,
    v.is_tronco_abi,
    v.vigente_de,
    v.vigente_ate,
    v.vigente_ate is null as is_atual
from versoes v
left join {{ ref('int_atributos_curso') }} atual on atual.nome_curso = v.nome_curso
