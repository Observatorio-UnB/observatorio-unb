-- Distribuição de semestres até a formatura de um curso canônico, nas coortes maduras
-- (2010 a 2016). É o detalhamento por curso do painel e do caso de uso de orientação ao
-- calouro: "em quantos semestres os formados deste curso de fato se formam?".
--
-- Reproduzir (banco do docker compose, depois do pipeline e do autovacuum):
--   docker compose exec -T db psql -U observatorio -d observatorio -f - < docs/explain/distribuicao_formatura_por_curso.sql
-- A consulta roda duas vezes; o plano versionado é o da segunda, com o cache quente.
EXPLAIN (ANALYZE, BUFFERS)
SELECT m.semestres_permanencia_valida AS semestres, count(*) AS formados
FROM silver.movimentacoes_vinculos m
JOIN silver.estruturas_curriculares e USING (id_estrutura)
WHERE e.nome_curso_canonico = 'CIENCIA DA COMPUTACAO'
  AND m.tipo_saida_grupo = 'FORMATURA'
  AND m.ano_ingresso BETWEEN 2010 AND 2016
GROUP BY 1
ORDER BY 1;
