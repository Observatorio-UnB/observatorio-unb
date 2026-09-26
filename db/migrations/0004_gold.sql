-- Camada gold: saída de src/pipeline/build_gold.py, agregada por curso.
-- O CHECK de k >= 5 transforma a regra de supressão ética do pipeline em
-- garantia do banco: um grupo pequeno não entra nem por engano.

CREATE TABLE gold.retencao_cursos_unb (
  curso                         TEXT PRIMARY KEY,
  departamento                  TEXT,
  campus                        TEXT,
  turno                         TEXT CHECK (turno IN ('DIURNO', 'NOTURNO', 'INTEGRAL')),
  area_conhecimento             TEXT,
  grau_academico                TEXT,
  categoria_grau                TEXT CHECK (categoria_grau IN ('BACHARELADO', 'LICENCIATURA', 'MISTO')),
  semestre_minimo_previsto      NUMERIC(4,1),
  semestre_ideal_previsto       NUMERIC(4,1),
  semestre_maximo_previsto      NUMERIC(4,1),
  carga_horaria_minima          INTEGER,
  total_discentes_registrados   INTEGER NOT NULL CHECK (total_discentes_registrados >= 5),
  total_formados                INTEGER NOT NULL CHECK (total_formados >= 0),
  total_evadidos_desligados     INTEGER NOT NULL CHECK (total_evadidos_desligados >= 0),
  taxa_formatura_pct            NUMERIC(5,2) CHECK (taxa_formatura_pct BETWEEN 0 AND 100),
  taxa_evasao_pct               NUMERIC(5,2) CHECK (taxa_evasao_pct BETWEEN 0 AND 100),
  formados_tempo_minimo_pct     NUMERIC(5,2) CHECK (formados_tempo_minimo_pct BETWEEN 0 AND 100),
  formados_tempo_ideal_pct      NUMERIC(5,2) CHECK (formados_tempo_ideal_pct BETWEEN 0 AND 100),
  formados_acima_ideal_pct      NUMERIC(5,2) CHECK (formados_acima_ideal_pct BETWEEN 0 AND 100),
  formados_limite_maximo_pct    NUMERIC(5,2) CHECK (formados_limite_maximo_pct BETWEEN 0 AND 100),
  tempo_medio_real_semestres    NUMERIC(5,2),
  tempo_mediano_real_semestres  NUMERIC(5,2),
  desvio_medio_semestres        NUMERIC(5,2),
  indice_retencao_critica       NUMERIC(4,1) CHECK (indice_retencao_critica BETWEEN 0 AND 100),
  classificacao_retencao        TEXT CHECK (classificacao_retencao IN
                                  ('RETENÇÃO CRÍTICA', 'RETENÇÃO ALTA', 'RETENÇÃO MÉDIA', 'RETENÇÃO BAIXA')),
  pibic_total_projetos          INTEGER,
  pibic_bolsas_remuneradas      INTEGER,
  pibic_bolsas_voluntarias      INTEGER,
  pibic_cotistas                INTEGER,
  pibic_investimento_total      NUMERIC(14,2),
  pibic_projetos_por_100_alunos NUMERIC(7,2),
  CHECK (total_formados + total_evadidos_desligados <= total_discentes_registrados)
);
COMMENT ON TABLE gold.retencao_cursos_unb IS
  'Retenção, formatura e evasão por curso. Uma linha por curso canônico de graduação; cursos com bacharelado e licenciatura sob o mesmo nome ficam numa linha só (categoria_grau = MISTO). Só entram cursos com 5 ou mais discentes.';
COMMENT ON COLUMN gold.retencao_cursos_unb.curso IS 'Nome canônico do curso após a harmonização SIGRA -> matriz curricular (sem acento, maiúsculas).';
COMMENT ON COLUMN gold.retencao_cursos_unb.departamento IS 'Departamento de vinculação, como registrado no SIGRA.';
COMMENT ON COLUMN gold.retencao_cursos_unb.campus IS 'Campus de oferta.';
COMMENT ON COLUMN gold.retencao_cursos_unb.turno IS 'DIURNO, NOTURNO ou INTEGRAL. Matutino e vespertino são unificados em DIURNO.';
COMMENT ON COLUMN gold.retencao_cursos_unb.area_conhecimento IS 'Grande Área CNPq/MEC.';
COMMENT ON COLUMN gold.retencao_cursos_unb.grau_academico IS 'Titulação literal conferida ao egresso, ou MISTO (BACHARELADO + LICENCIATURA).';
COMMENT ON COLUMN gold.retencao_cursos_unb.categoria_grau IS 'BACHARELADO (inclui titulações profissionais), LICENCIATURA ou MISTO.';
COMMENT ON COLUMN gold.retencao_cursos_unb.semestre_minimo_previsto IS 'Prazo mínimo regulamentar, em semestres.';
COMMENT ON COLUMN gold.retencao_cursos_unb.semestre_ideal_previsto IS 'Duração ideal da matriz curricular, em semestres.';
COMMENT ON COLUMN gold.retencao_cursos_unb.semestre_maximo_previsto IS 'Prazo máximo antes do jubilamento, em semestres.';
COMMENT ON COLUMN gold.retencao_cursos_unb.carga_horaria_minima IS 'Carga horária total mínima para conclusão, em horas.';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_discentes_registrados IS 'Vínculos do curso no SIGRA. Mínimo 5 (supressão de grupos pequenos, k-anonimato).';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_formados IS 'Vínculos com saída por formatura.';
COMMENT ON COLUMN gold.retencao_cursos_unb.total_evadidos_desligados IS 'Vínculos encerrados por abandono, jubilamento, 3 reprovações ou desligamento.';
COMMENT ON COLUMN gold.retencao_cursos_unb.taxa_formatura_pct IS 'total_formados / total_discentes_registrados x 100.';
COMMENT ON COLUMN gold.retencao_cursos_unb.taxa_evasao_pct IS 'total_evadidos_desligados / total_discentes_registrados x 100.';
COMMENT ON COLUMN gold.retencao_cursos_unb.formados_tempo_minimo_pct IS '% dos formados que concluíram em semestres <= semestre_minimo_previsto.';
COMMENT ON COLUMN gold.retencao_cursos_unb.formados_tempo_ideal_pct IS '% dos formados que concluíram em semestres <= semestre_ideal_previsto.';
COMMENT ON COLUMN gold.retencao_cursos_unb.formados_acima_ideal_pct IS '% dos formados que passaram do semestre_ideal_previsto.';
COMMENT ON COLUMN gold.retencao_cursos_unb.formados_limite_maximo_pct IS '% dos formados que concluíram em semestres >= semestre_maximo_previsto.';
COMMENT ON COLUMN gold.retencao_cursos_unb.tempo_medio_real_semestres IS 'Média de semestres entre ingresso e formatura, entre os formados.';
COMMENT ON COLUMN gold.retencao_cursos_unb.tempo_mediano_real_semestres IS 'Mediana de semestres entre ingresso e formatura, entre os formados.';
COMMENT ON COLUMN gold.retencao_cursos_unb.desvio_medio_semestres IS 'Média de (semestres cursados - semestre_ideal_previsto) entre os formados. Negativo = formou antes do ideal.';
COMMENT ON COLUMN gold.retencao_cursos_unb.indice_retencao_critica IS 'IRC, 0 a 100: (0,3 x atraso normalizado + 0,7 x evasão normalizada) x 100, com saturação nos percentis 5 e 95.';
COMMENT ON COLUMN gold.retencao_cursos_unb.classificacao_retencao IS 'Quartil do IRC: CRÍTICA (>= p75), ALTA (>= p50), MÉDIA (>= p25), BAIXA.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_total_projetos IS 'Planos de iniciação científica de alunos do curso, em todos os anos publicados. Zero quando não há plano.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_bolsas_remuneradas IS 'Planos com bolsa remunerada (PIBIC). Nulo quando o curso não tem plano de IC.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_bolsas_voluntarias IS 'Planos voluntários (PIVIC). Nulo quando o curso não tem plano de IC.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_cotistas IS 'Planos de bolsistas que ingressaram por cota. Nulo quando o curso não tem plano de IC.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_investimento_total IS 'Soma estimada das bolsas remuneradas do curso, em R$.';
COMMENT ON COLUMN gold.retencao_cursos_unb.pibic_projetos_por_100_alunos IS 'pibic_total_projetos / total_discentes_registrados x 100.';

CREATE TABLE gold.pibic_social_unb (
  curso_pibic_norm        TEXT NOT NULL,
  campus                  TEXT NOT NULL,
  area_conhecimento       TEXT,
  total_projetos          INTEGER NOT NULL CHECK (total_projetos >= 5),
  total_remuneradas       INTEGER NOT NULL CHECK (total_remuneradas >= 0),
  total_voluntarias_pivic INTEGER NOT NULL CHECK (total_voluntarias_pivic >= 0),
  total_cotistas          INTEGER NOT NULL CHECK (total_cotistas >= 0),
  total_cotistas_ppi      INTEGER NOT NULL CHECK (total_cotistas_ppi >= 0),
  total_baixa_renda       INTEGER NOT NULL CHECK (total_baixa_renda >= 0),
  valor_total_investido   NUMERIC(14,2) NOT NULL CHECK (valor_total_investido >= 0),
  taxa_cotistas_pct       NUMERIC(5,2) CHECK (taxa_cotistas_pct BETWEEN 0 AND 100),
  taxa_voluntario_pct     NUMERIC(5,2) CHECK (taxa_voluntario_pct BETWEEN 0 AND 100),
  PRIMARY KEY (curso_pibic_norm, campus)
);
COMMENT ON TABLE gold.pibic_social_unb IS
  'Iniciação científica por curso e campus: volume, bolsas e perfil social dos bolsistas. Só entram grupos com 5 ou mais planos.';
COMMENT ON COLUMN gold.pibic_social_unb.curso_pibic_norm IS 'Curso do bolsista, já harmonizado com os nomes canônicos.';
COMMENT ON COLUMN gold.pibic_social_unb.total_projetos IS 'Planos de trabalho de IC. Mínimo 5 (k-anonimato).';
COMMENT ON COLUMN gold.pibic_social_unb.total_remuneradas IS 'Planos com bolsa remunerada (PIBIC).';
COMMENT ON COLUMN gold.pibic_social_unb.total_voluntarias_pivic IS 'Planos voluntários (PIVIC).';
COMMENT ON COLUMN gold.pibic_social_unb.total_cotistas IS 'Planos de bolsistas que ingressaram por cota.';
COMMENT ON COLUMN gold.pibic_social_unb.total_cotistas_ppi IS 'Planos de bolsistas classificados como PPI / ETNICO-RACIAL. Atenção: hoje inclui cotas "NÃO PPI" (ver silver.pibic_bolsistas.perfil_social_macro).';
COMMENT ON COLUMN gold.pibic_social_unb.total_baixa_renda IS 'Planos de bolsistas que ingressaram por cota de baixa renda (até 1,5 salário mínimo per capita).';
COMMENT ON COLUMN gold.pibic_social_unb.valor_total_investido IS 'Soma estimada das bolsas remuneradas, em R$.';
COMMENT ON COLUMN gold.pibic_social_unb.taxa_cotistas_pct IS 'total_cotistas / total_projetos x 100.';
COMMENT ON COLUMN gold.pibic_social_unb.taxa_voluntario_pct IS 'total_voluntarias_pivic / total_projetos x 100.';

CREATE TABLE gold.regras_harmonizacao_canonicas (
  origem_sigra         TEXT PRIMARY KEY,
  destino_estrutura    TEXT NOT NULL,
  categoria            TEXT,
  justificativa        TEXT,
  discentes_impactados INTEGER NOT NULL CHECK (discentes_impactados >= 0)
);
COMMENT ON TABLE gold.regras_harmonizacao_canonicas IS
  'Regras de equivalência entre o nome do curso no SIGRA e o nome da matriz curricular (entity resolution). Uma linha por nome de origem.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.origem_sigra IS 'Nome normalizado do curso como aparece no SIGRA.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.destino_estrutura IS 'Nome da matriz em silver.estrutura_curricular para o qual a origem é mapeada.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.discentes_impactados IS 'Vínculos do SIGRA reclassificados por esta regra.';

CREATE TABLE gold.relatorios (
  nome          TEXT PRIMARY KEY,
  conteudo      JSONB NOT NULL,
  _carregado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE gold.relatorios IS
  'Relatórios JSON do pipeline: métricas gerais da UnB, métricas do PIBIC e auditoria de casamento dos joins. Uma linha por arquivo.';
COMMENT ON COLUMN gold.relatorios.nome IS 'Nome do arquivo de origem sem extensão (ex.: metricas_gerais_unb).';
COMMENT ON COLUMN gold.relatorios.conteudo IS 'Conteúdo integral do JSON.';

COMMENT ON COLUMN gold.pibic_social_unb.campus IS 'Campus inferido da unidade do bolsista.';
COMMENT ON COLUMN gold.pibic_social_unb.area_conhecimento IS 'Grande Área CNPq/MEC do curso.';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.categoria IS 'Motivo agrupado da regra (Correção de Typo no Portal, Habilitação Legada, Engenharias...).';
COMMENT ON COLUMN gold.regras_harmonizacao_canonicas.justificativa IS 'Explicação da equivalência, em texto.';
COMMENT ON COLUMN gold.relatorios._carregado_em IS 'Momento em que o relatório foi carregado no banco.';
