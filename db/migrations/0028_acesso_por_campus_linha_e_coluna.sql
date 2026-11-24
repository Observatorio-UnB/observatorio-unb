-- ============================================================================
-- Migração 0028: Acesso por campus aos vínculos, com recorte de linha (RLS) e de coluna
--
-- Até aqui havia dois níveis (ADR 0010): o papel observatorio_leitura, que só lê o agregado (gold,
-- busca, dbt_marts), e o dono do banco, que lê tudo. Quem precisa do vínculo individual para
-- trabalhar, como a secretaria acadêmica de um campus que acompanha os próprios alunos, só tinha a
-- segunda opção: o dono, com os quatro campi e o id_discente que liga o vínculo à pessoa.
--
-- O papel secretaria_campus aplica privilégio mínimo nas duas direções:
--   - linha (RLS): só os vínculos de cursos dos campi em que o usuário está lotado
--     (acesso.lotacao_campus). Sem lotação, nenhuma linha;
--   - coluna: todas as colunas do vínculo menos id_discente. Sem ele o vínculo não se liga a
--     silver.discentes (nascimento, sexo, raça/cor), que o papel também não lê.
--
-- A lotação também tem RLS: cada usuário só vê as próprias linhas. O pipeline grava como dono da tabela, que não
-- passa pela RLS (sem FORCE ROW LEVEL SECURITY): a carga e o CDC continuam iguais.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS acesso;
COMMENT ON SCHEMA acesso IS 'Lotação dos usuários que leem a silver com recorte de linha.';

CREATE TABLE IF NOT EXISTS acesso.lotacao_campus (
    usuario       name        NOT NULL,
    campus        text        NOT NULL,
    concedido_em  timestamptz NOT NULL DEFAULT now(),
    concedido_por name        NOT NULL DEFAULT current_user,
    PRIMARY KEY (usuario, campus)
);
COMMENT ON TABLE acesso.lotacao_campus IS
  'Campi cujos vínculos cada usuário do papel secretaria_campus enxerga. Apagar a linha revoga o acesso.';

-- O papel lê a lotação, mas só as próprias linhas (RLS também aqui): não descobre quem mais tem
-- acesso a quê. current_user, e não session_user: vale o papel ativo (SET ROLE).
ALTER TABLE acesso.lotacao_campus ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS so_a_propria_lotacao ON acesso.lotacao_campus;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'secretaria_campus') THEN
    CREATE ROLE secretaria_campus NOLOGIN;
  END IF;
END
$$;
COMMENT ON ROLE secretaria_campus IS
  'Secretaria acadêmica de campus: vínculos só dos campi lotados (RLS), sem id_discente (coluna). Sem acesso a discentes.';

GRANT USAGE ON SCHEMA acesso TO secretaria_campus;
GRANT SELECT ON acesso.lotacao_campus TO secretaria_campus;
CREATE POLICY so_a_propria_lotacao ON acesso.lotacao_campus
    FOR SELECT TO secretaria_campus
    USING (usuario = current_user);

-- Catálogo de cursos e matrizes: sem dado pessoal, e necessário para a política e para as consultas.
GRANT USAGE ON SCHEMA silver TO secretaria_campus;
GRANT SELECT ON silver.cursos, silver.estruturas_curriculares TO secretaria_campus;

-- Recorte de coluna: tudo menos id_discente. Só na tabela-mãe: as partições não têm grant, então
-- não servem de atalho para fugir da política.
GRANT SELECT (id_vinculo, id_curso, id_estrutura, ano_ingresso, semestre_ingresso, forma_saida,
              tipo_saida_grupo, ano_saida, semestre_saida, semestres_permanencia,
              semestres_permanencia_valida, periodo_saida_estimado, status_aluno, fonte)
    ON silver.movimentacoes_vinculos TO secretaria_campus;

-- Recorte de linha.
ALTER TABLE silver.movimentacoes_vinculos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vinculos_do_campus_lotado ON silver.movimentacoes_vinculos;
-- = ANY(ARRAY(...)): a lista de cursos do usuário é calculada uma vez (InitPlan) e vira condição do
-- índice (id_curso, ano_ingresso) de cada partição. Com IN (subconsulta), o PostgreSQL testava cada
-- linha contra um subplano com hash, varrendo as 152 mil: 7,9 ms contra 0,6 ms na contagem da FCTE.
CREATE POLICY vinculos_do_campus_lotado ON silver.movimentacoes_vinculos
    FOR SELECT TO secretaria_campus
    USING (id_curso = ANY (ARRAY(
        SELECT c.id_curso FROM silver.cursos c
        JOIN acesso.lotacao_campus l ON l.campus = c.campus
        WHERE l.usuario = current_user
    )));

COMMENT ON POLICY vinculos_do_campus_lotado ON silver.movimentacoes_vinculos IS
  'secretaria_campus vê só os vínculos de cursos dos campi em acesso.lotacao_campus para o usuário.';
