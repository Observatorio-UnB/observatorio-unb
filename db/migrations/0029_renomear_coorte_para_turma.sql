-- Nomenclatura: "coorte" vira "turma". As migrações 0007 a 0028 já foram aplicadas e não podem ser
-- editadas (checksum em public.schema_migrations), então o nome novo entra por aqui.

ALTER TABLE gold.retencao_cursos_coorte RENAME TO retencao_cursos_turma;
ALTER TABLE gold.retencao_cursos_turma RENAME COLUMN coorte_madura TO turma_madura;
ALTER TABLE silver.cargas_vinculos RENAME COLUMN ultima_coorte_madura TO ultima_turma_madura;
ALTER VIEW silver.chegadas_por_carga RENAME COLUMN coorte_publicada TO turma_publicada;
ALTER PROCEDURE gold.atualizar_retencao_coorte(integer) RENAME TO atualizar_retencao_turma;
ALTER TABLE gold.retencao_cursos_turma RENAME CONSTRAINT retencao_cursos_coorte_pkey TO retencao_cursos_turma_pkey;

-- Funções SQL são validadas na criação: sem isso, a ordem de recriação abaixo poderia falhar.
SET LOCAL check_function_bodies = off;

-- O corpo das rotinas é texto e o PostgreSQL não o acompanha no RENAME: recria cada rotina que
-- ainda cita o nome antigo, trocando o texto na definição.
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT p.oid
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ('gold', 'silver', 'public') AND p.prosrc ~* 'coorte'
    LOOP
        EXECUTE replace(replace(replace(pg_get_functiondef(r.oid), 'coorte', 'turma'), 'Coorte', 'Turma'), 'COORTE', 'TURMA');
    END LOOP;
END $$;

-- Os COMMENT ON (fonte do dicionário de dados) também trocam o texto.
DO $$
DECLARE
    r record;
    alvo text;
BEGIN
    FOR r IN
        SELECT d.classoid::regclass::text AS catalogo, d.objoid, d.objsubid, d.description
        FROM pg_description d
        WHERE d.description ~* 'coorte' AND d.classoid IN ('pg_class'::regclass, 'pg_proc'::regclass)
    LOOP
        IF r.catalogo = 'pg_proc' THEN
            SELECT CASE prokind WHEN 'p' THEN 'PROCEDURE ' ELSE 'FUNCTION ' END || r.objoid::regprocedure::text
              INTO alvo FROM pg_proc WHERE oid = r.objoid;
        ELSE
            SELECT CASE WHEN r.objsubid > 0
                        THEN 'COLUMN ' || r.objoid::regclass::text || '.' ||
                             quote_ident((SELECT attname FROM pg_attribute WHERE attrelid = r.objoid AND attnum = r.objsubid))
                        WHEN c.relkind = 'v' THEN 'VIEW ' || r.objoid::regclass::text
                        WHEN c.relkind = 'm' THEN 'MATERIALIZED VIEW ' || r.objoid::regclass::text
                        WHEN c.relkind IN ('i', 'I') THEN 'INDEX ' || r.objoid::regclass::text
                        ELSE 'TABLE ' || r.objoid::regclass::text END
              INTO alvo FROM pg_class c WHERE c.oid = r.objoid;
        END IF;
        EXECUTE format('COMMENT ON %s IS %L', alvo,
                       replace(replace(replace(r.description, 'coorte', 'turma'), 'Coorte', 'Turma'), 'COORTE', 'TURMA'));
    END LOOP;
END $$;
