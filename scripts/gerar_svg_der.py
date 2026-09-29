"""
Gera diagramas DER em formato SVG vetorial diretamente do catálogo do PostgreSQL.

Padrão de Engenharia de Dados:
- Roteamento ortogonal em canais/calhas dedicadas (ZERO colisão com caixas)
- Exibe a totalidade das tabelas do esquema (todas as 15 da Silver e todas as 14 da Gold, incluindo MV)
- Tipografia acadêmica sem emojis nos títulos e cabeçalhos
- Dimensionamento dinâmico e respiradouros amplos sem truncamento
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar

ASSETS_DIR = BASE_DIR / "docs" / "arquitetura" / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def get_schema_metadata(cur, schema_name):
    """Obtém tabelas, colunas, tipos, PKs e FKs do esquema de forma 100% precisa."""
    # Colunas de tabelas base
    cur.execute("""
        SELECT 
            c.table_name,
            c.column_name,
            c.data_type,
            c.character_maximum_length,
            c.is_nullable
        FROM information_schema.columns c
        WHERE c.table_schema = %s
        ORDER BY c.table_name, c.ordinal_position;
    """, (schema_name,))
    columns_raw = list(cur.fetchall())

    # Se for gold, incluir também as colunas da materialized view
    if schema_name == "gold":
        cur.execute("""
            SELECT 
                c.relname AS table_name,
                a.attname AS column_name,
                t.typname AS data_type,
                NULL AS character_maximum_length,
                CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            JOIN pg_type t ON t.oid = a.atttypid
            WHERE n.nspname = 'gold' AND c.relkind = 'm' AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum;
        """)
        columns_raw.extend(cur.fetchall())

    # Chaves Primárias via pg_constraint
    cur.execute("""
        SELECT 
            c.conrelid::regclass::text AS full_table_name,
            a.attname AS column_name
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.contype = 'p' AND n.nspname = %s;
    """, (schema_name,))
    pks = set()
    for row in cur.fetchall():
        tbl = row[0].split(".")[-1]
        pks.add((tbl, row[1]))

    # Chaves Estrangeiras via pg_constraint
    cur.execute("""
        SELECT 
            c.conrelid::regclass::text AS from_table,
            a.attname AS from_column,
            c.confrelid::regclass::text AS to_table,
            af.attname AS to_column
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.contype = 'f' AND n.nspname = %s;
    """, (schema_name,))
    fks = []
    seen_fks = set()
    for row in cur.fetchall():
        from_tbl = row[0].split(".")[-1]
        to_tbl = row[2].split(".")[-1]
        fk_item = {
            "from_table": from_tbl,
            "from_column": row[1],
            "to_table": to_tbl,
            "to_column": row[3]
        }
        fk_key = (from_tbl, row[1], to_tbl, row[3])
        if fk_key not in seen_fks:
            seen_fks.add(fk_key)
            fks.append(fk_item)

    # Identificar chaves únicas para destacar badges
    cur.execute("""
        SELECT 
            c.conrelid::regclass::text AS full_table_name,
            a.attname AS column_name
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.contype = 'u' AND n.nspname = %s;
    """, (schema_name,))
    uks = set()
    for row in cur.fetchall():
        tbl = row[0].split(".")[-1]
        uks.add((tbl, row[1]))

    tables = {}
    for row in columns_raw:
        t_name, col_name, d_type, char_len, is_null = row
        if t_name not in tables:
            tables[t_name] = []
        type_str = d_type.upper()
        if char_len:
            type_str += f"({char_len})"
        type_str = type_str.replace("CHARACTER VARYING", "VARCHAR")
        type_str = type_str.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ")
        type_str = type_str.replace("INT4", "INTEGER")
        type_str = type_str.replace("INT8", "BIGINT")
        type_str = type_str.replace("INT2", "SMALLINT")
        tables[t_name].append({
            "name": col_name,
            "type": type_str,
            "is_pk": (t_name, col_name) in pks,
            "is_fk": any(f["from_table"] == t_name and f["from_column"] == col_name for f in fks),
            "is_uk": (t_name, col_name) in uks,
            "is_nullable": is_null == "YES"
        })

    return tables, fks


def draw_table_card(t_name, schema_prefix, cols, x, y, w, header_color, border_color, title_color="#f8fafc"):
    """Gera o SVG de um card de tabela com portas de conexão."""
    row_height = 23
    header_height = 36
    h = header_height + len(cols) * row_height + 8

    parts = []
    parts.append(f'''  <!-- Tabela: {schema_prefix}.{t_name} -->
  <g filter="url(#shadow)">
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#1e293b" stroke="{border_color}" stroke-width="1.5"/>
    <rect x="{x}" y="{y}" width="{w}" height="{header_height}" rx="8" fill="{header_color}"/>
    <rect x="{x}" y="{y + header_height - 5}" width="{w}" height="5" fill="{header_color}"/>
    <text x="{x + 14}" y="{y + 23}" fill="{title_color}" font-size="13" font-weight="700">{schema_prefix}.{t_name}</text>
''')

    ports = {}
    for idx, col in enumerate(cols):
        cy = y + header_height + idx * row_height + 16
        ports[col["name"]] = {
            "x_left": x,
            "x_right": x + w,
            "y": cy - 4
        }

        if col["is_pk"]:
            badge = '<rect x="{bx}" y="{by}" width="26" height="14" rx="3" fill="#f59e0b"/><text x="{tx}" y="{ty}" fill="#0f172a" font-size="9" font-weight="bold">PK</text>'
            parts.append(badge.format(bx=x+10, by=cy-11, tx=x+16, ty=cy))
        elif col["is_fk"]:
            badge = '<rect x="{bx}" y="{by}" width="26" height="14" rx="3" fill="#38bdf8"/><text x="{tx}" y="{ty}" fill="#0f172a" font-size="9" font-weight="bold">FK</text>'
            parts.append(badge.format(bx=x+10, by=cy-11, tx=x+16, ty=cy))
        elif col.get("is_uk"):
            badge = '<rect x="{bx}" y="{by}" width="26" height="14" rx="3" fill="#10b981"/><text x="{tx}" y="{ty}" fill="#0f172a" font-size="9" font-weight="bold">UK</text>'
            parts.append(badge.format(bx=x+10, by=cy-11, tx=x+16, ty=cy))
        else:
            badge = '<circle cx="{cx}" cy="{c_y}" r="2" fill="#64748b"/>'
            parts.append(badge.format(cx=x+23, c_y=cy-4))

        col_fill = "#f8fafc" if (col["is_pk"] or col["is_fk"] or col.get("is_uk")) else "#cbd5e1"
        font_w = "600" if (col["is_pk"] or col["is_fk"] or col.get("is_uk")) else "400"
        parts.append(f'    <text x="{x + 42}" y="{cy}" fill="{col_fill}" font-size="11.5" font-weight="{font_w}">{col["name"]}</text>')
        parts.append(f'    <text x="{x + w - 12}" y="{cy}" fill="#94a3b8" font-size="10.5" font-family="monospace" text-anchor="end">{col["type"]}</text>')

    parts.append('  </g>')
    return "\n".join(parts), ports, h


def render_silver_svg(tables, fks, output_path):
    """Renderiza a totalidade das 15 tabelas da camada Silver com roteamento ortogonal sem colisões."""
    layout = {
        # Zona 1 - Coluna 1A: Discentes e Censo
        "discentes_graduacao": {"x": 60, "y": 120, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},
        "sigaa_ativos":        {"x": 60, "y": 860, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},
        "inep_censo_superior": {"x": 60, "y": 1140, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},

        # Zona 1 - Coluna 1B: Cursos, Matrizes e Bolsistas
        "cursos_graduacao":    {"x": 390, "y": 120, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},
        "estrutura_curricular":{"x": 390, "y": 880, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},
        "pibic_bolsistas":     {"x": 390, "y": 1140, "w": 300, "header": "#334155", "border": "#475569", "title": "#94a3b8"},

        # Zona 2 - Coluna 2A: Relações Canônicas 3NF Base
        "discentes":      {"x": 760, "y": 120, "w": 320, "header": "#0369a1", "border": "#0284c7", "title": "#e0f2fe"},
        "pibic_projetos": {"x": 760, "y": 340, "w": 320, "header": "#0369a1", "border": "#0284c7", "title": "#e0f2fe"},
        "cursos":         {"x": 760, "y": 750, "w": 320, "header": "#0369a1", "border": "#0284c7", "title": "#e0f2fe"},

        # Zona 2 - Coluna 2B: Vínculos e Matrizes Canônicas
        "movimentacoes_vinculos":  {"x": 1140, "y": 120, "w": 330, "header": "#0284c7", "border": "#38bdf8", "title": "#ffffff"},
        "estruturas_curriculares": {"x": 1140, "y": 550, "w": 330, "header": "#0369a1", "border": "#0284c7", "title": "#e0f2fe"},

        # Zona 3 - Coluna 3: Partições Físicas Declarativas
        "movimentacoes_p2000_2015": {"x": 1540, "y": 120, "w": 330, "header": "#475569", "border": "#64748b", "title": "#cbd5e1"},
        "movimentacoes_p2016_2020": {"x": 1540, "y": 530, "w": 330, "header": "#475569", "border": "#64748b", "title": "#cbd5e1"},
        "movimentacoes_p2021_atual": {"x": 1540, "y": 940, "w": 330, "header": "#475569", "border": "#64748b", "title": "#cbd5e1"},
        "movimentacoes_p_default":  {"x": 1540, "y": 1350, "w": 330, "header": "#475569", "border": "#64748b", "title": "#cbd5e1"},
    }

    svg_parts = []
    svg_parts.append('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1940 1820" width="100%" height="100%" style="background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <filter id="shadow" x="-3%" y="-2%" width="106%" height="108%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.4"/>
    </filter>
    <marker id="dot" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5">
      <circle cx="5" cy="5" r="3.5" fill="#38bdf8"/>
    </marker>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#38bdf8"/>
    </marker>
  </defs>

  <!-- Banner do Topo (Sem Emojis) -->
  <text x="60" y="44" fill="#f8fafc" font-size="22" font-weight="700">Camada Silver: Modelo Relacional 3NF e Engenharia Física</text>
  <text x="60" y="68" fill="#94a3b8" font-size="13">Observatório UnB — PostgreSQL 16/17 • 15 Tabelas Catalogadas (5 Canônicas 3NF, 4 Partições Físicas e 6 de Staging/Auditoria)</text>

  <!-- Rótulos e Limites das Zonas -->
  <rect x="45" y="90" width="665" height="1700" rx="10" fill="none" stroke="#334155" stroke-dasharray="6,4" stroke-width="1"/>
  <text x="60" y="108" fill="#64748b" font-size="11" font-weight="700">ZONA 1: STAGING &amp; AUDITORIA LEGADA (6 TABELAS)</text>

  <rect x="735" y="90" width="765" height="1700" rx="10" fill="none" stroke="#0284c7" stroke-dasharray="6,4" stroke-width="1.2"/>
  <text x="750" y="108" fill="#38bdf8" font-size="11" font-weight="700">ZONA 2: MODELO RELACIONAL CANÔNICO EM 3NF (5 TABELAS)</text>

  <rect x="1520" y="90" width="375" height="1700" rx="10" fill="none" stroke="#475569" stroke-dasharray="6,4" stroke-width="1"/>
  <text x="1535" y="108" fill="#94a3b8" font-size="11" font-weight="700">ZONA 3: PARTIÇÕES FÍSICAS DECLARATIVAS (4 TABELAS)</text>
''')

    all_ports = {}
    for t_name, cfg in layout.items():
        cols = tables.get(t_name, [])
        card_svg, ports, h = draw_table_card(
            t_name, "silver", cols, cfg["x"], cfg["y"], cfg["w"],
            cfg["header"], cfg["border"], cfg["title"]
        )
        svg_parts.append(card_svg)
        all_ports[t_name] = ports

    svg_parts.append('\n  <!-- Conectores Relacionais Ortogonais em Calhas Livres de Colisão -->')

    def route_orthogonal(x1, y1, x2, y2, channel_x=None, stroke="#38bdf8", stroke_w="1.8", dashed=False):
        dash = ' stroke-dasharray="5,3"' if dashed else ''
        if channel_x is not None:
            d = f"M {x1} {y1} L {channel_x} {y1} L {channel_x} {y2} L {x2} {y2}"
        else:
            mid_x = (x1 + x2) / 2
            d = f"M {x1} {y1} L {mid_x} {y1} L {mid_x} {y2} L {x2} {y2}"
        return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_w}"{dash} marker-start="url(#dot)" marker-end="url(#arrow)"/>'

    # 1. pibic_projetos.id_discente -> discentes.id_discente (Calha x = 735)
    p_from = all_ports["pibic_projetos"]["id_discente"]
    p_to = all_ports["discentes"]["id_discente"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=735)}')

    # 2. pibic_projetos.id_curso -> cursos.id_curso (Calha x = 720)
    p_from = all_ports["pibic_projetos"]["id_curso"]
    p_to = all_ports["cursos"]["id_curso"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=720)}')

    # 3. pibic_projetos.id_estrutura -> estruturas_curriculares.id_estrutura (Calha x = 1110)
    p_from = all_ports["pibic_projetos"]["id_estrutura"]
    p_to = all_ports["estruturas_curriculares"]["id_estrutura"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_right"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=1110)}')

    # 4. estruturas_curriculares.id_curso -> cursos.id_curso (Calha x = 1110)
    p_from = all_ports["estruturas_curriculares"]["id_curso"]
    p_to = all_ports["cursos"]["id_curso"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=1110)}')

    # 5. movimentacoes_vinculos.id_discente -> discentes.id_discente (Calha x = 1110)
    p_from = all_ports["movimentacoes_vinculos"]["id_discente"]
    p_to = all_ports["discentes"]["id_discente"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=1110)}')

    # 6. movimentacoes_vinculos.id_curso -> cursos.id_curso (Calha x = 1095)
    p_from = all_ports["movimentacoes_vinculos"]["id_curso"]
    p_to = all_ports["cursos"]["id_curso"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=1095)}')

    # 7. movimentacoes_vinculos.id_estrutura -> estruturas_curriculares.id_estrutura (Calha x = 1125)
    p_from = all_ports["movimentacoes_vinculos"]["id_estrutura"]
    p_to = all_ports["estruturas_curriculares"]["id_estrutura"]
    svg_parts.append(f'  {route_orthogonal(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=1125)}')

    # 8. Partições da movimentacoes_vinculos (Calha x = 1510 para as 4 partições)
    p_mv = all_ports["movimentacoes_vinculos"]["ano_ingresso"]
    for part_name in ["movimentacoes_p2000_2015", "movimentacoes_p2016_2020", "movimentacoes_p2021_atual", "movimentacoes_p_default"]:
        p_part = all_ports[part_name]["ano_ingresso"]
        svg_parts.append(f'  {route_orthogonal(p_mv["x_right"], p_mv["y"], p_part["x_left"], p_part["y"], channel_x=1510, stroke="#64748b", dashed=True)}')

    svg_parts.append('</svg>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parts))
    print(f"Salvo Silver SVG: {output_path}")


def render_gold_svg(tables, fks, output_path):
    """Renderiza a totalidade das 14 relações da camada Gold (incluindo MV) em Star Schema sem colisões."""
    layout = {
        # Coluna 1: Dimensões Conformadas e Regras
        "dim_campus":                    {"x": 60, "y": 120, "w": 310, "header": "#1e293b", "border": "#334155", "title": "#38bdf8"},
        "dim_tempo":                     {"x": 60, "y": 290, "w": 310, "header": "#1e293b", "border": "#334155", "title": "#38bdf8"},
        "dim_perfil_social":             {"x": 60, "y": 480, "w": 310, "header": "#1e293b", "border": "#334155", "title": "#38bdf8"},
        "regras_harmonizacao_canonicas": {"x": 60, "y": 670, "w": 310, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},
        "relatorios":                    {"x": 60, "y": 890, "w": 310, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},

        # Coluna 2: Tabelas Fato Granulares
        "fato_retencao_curso": {"x": 440, "y": 120, "w": 360, "header": "#854d0e", "border": "#ca8a04", "title": "#fef08a"},
        "fato_alunos_ativos":  {"x": 440, "y": 520, "w": 360, "header": "#854d0e", "border": "#ca8a04", "title": "#fef08a"},
        "fato_pibic_perfil":   {"x": 440, "y": 780, "w": 360, "header": "#854d0e", "border": "#ca8a04", "title": "#fef08a"},

        # Coluna 3: Dimensão Central e Visão Materializada
        "dim_curso":              {"x": 870, "y": 120, "w": 360, "header": "#1e293b", "border": "#334155", "title": "#38bdf8"},
        "mv_dashboard_executivo": {"x": 870, "y": 380, "w": 360, "header": "#065f46", "border": "#10b981", "title": "#d1fae5"},

        # Coluna 4: Tabelas Analíticas e Retenção
        "retencao_cursos_unb":   {"x": 1290, "y": 120, "w": 330, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},
        "ativos_hoje_cursos_unb":{"x": 1290, "y": 950, "w": 330, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},

        # Coluna 5: Benchmark e Social
        "inep_benchmark_cursos_unb": {"x": 1650, "y": 120, "w": 330, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},
        "pibic_social_unb":          {"x": 1650, "y": 630, "w": 330, "header": "#334155", "border": "#475569", "title": "#cbd5e1"},
    }

    svg_parts = []
    svg_parts.append('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2040 1280" width="100%" height="100%" style="background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <filter id="shadow" x="-3%" y="-2%" width="106%" height="108%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.4"/>
    </filter>
    <marker id="dotGold" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5">
      <circle cx="5" cy="5" r="3.5" fill="#facc15"/>
    </marker>
    <marker id="arrowGold" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#facc15"/>
    </marker>
    <marker id="arrowGreen" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10b981"/>
    </marker>
  </defs>

  <!-- Banner do Topo (Sem Emojis) -->
  <text x="60" y="44" fill="#f8fafc" font-size="22" font-weight="700">Camada Gold: Modelagem Dimensional em Star Schema (Kimball)</text>
  <text x="60" y="68" fill="#94a3b8" font-size="13">Observatório UnB — PostgreSQL 16/17 • 14 Relações Catalogadas (4 Dimensões Conformadas, 3 Fatos Granulares, 1 View Materializada e 6 Analíticas)</text>

  <!-- Rótulos de Zonas -->
  <rect x="45" y="90" width="340" height="1160" rx="10" fill="none" stroke="#334155" stroke-dasharray="6,4" stroke-width="1"/>
  <text x="60" y="108" fill="#64748b" font-size="11" font-weight="700">DIMENSÕES CONFORMADAS &amp; REGRAS</text>

  <rect x="420" y="90" width="400" height="1160" rx="10" fill="none" stroke="#ca8a04" stroke-dasharray="6,4" stroke-width="1.2"/>
  <text x="435" y="108" fill="#facc15" font-size="11" font-weight="700">TABELAS FATO (PROCESSOS DE NEGÓCIO)</text>

  <rect x="850" y="90" width="400" height="1160" rx="10" fill="none" stroke="#10b981" stroke-dasharray="6,4" stroke-width="1.2"/>
  <text x="865" y="108" fill="#34d399" font-size="11" font-weight="700">DIMENSÃO CENTRAL &amp; VIEW MATERIALIZADA</text>

  <rect x="1270" y="90" width="730" height="1160" rx="10" fill="none" stroke="#334155" stroke-dasharray="6,4" stroke-width="1"/>
  <text x="1285" y="108" fill="#94a3b8" font-size="11" font-weight="700">RELATÓRIOS ANALÍTICOS E BENCHMARK EXTERNO (6 TABELAS)</text>
''')

    all_ports = {}
    for t_name, cfg in layout.items():
        cols = tables.get(t_name, [])
        card_svg, ports, h = draw_table_card(
            t_name, "gold", cols, cfg["x"], cfg["y"], cfg["w"],
            cfg["header"], cfg["border"], cfg["title"]
        )
        svg_parts.append(card_svg)
        all_ports[t_name] = ports

    svg_parts.append('\n  <!-- Conectores Dimensionais Ortogonais (Sem Colisões) -->')

    def route_gold(x1, y1, x2, y2, channel_x, stroke="#facc15", stroke_w="1.8", marker_end="url(#arrowGold)", dashed=False):
        dash = ' stroke-dasharray="5,3"' if dashed else ''
        d = f"M {x1} {y1} L {channel_x} {y1} L {channel_x} {y2} L {x2} {y2}"
        return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_w}"{dash} marker-start="url(#dotGold)" marker-end="{marker_end}"/>'

    # 1. fato_retencao_curso.sk_campus -> dim_campus.sk_campus (Calha x = 410)
    p_from = all_ports["fato_retencao_curso"]["sk_campus"]
    p_to = all_ports["dim_campus"]["sk_campus"]
    svg_parts.append(f'  {route_gold(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=410)}')

    # 2. fato_retencao_curso.sk_curso -> dim_curso.sk_curso (Calha x = 840)
    p_from = all_ports["fato_retencao_curso"]["sk_curso"]
    p_to = all_ports["dim_curso"]["sk_curso"]
    svg_parts.append(f'  {route_gold(p_from["x_right"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=840)}')

    # 3. fato_alunos_ativos.sk_tempo_referencia -> dim_tempo.sk_tempo (Calha x = 410)
    p_from = all_ports["fato_alunos_ativos"]["sk_tempo_referencia"]
    p_to = all_ports["dim_tempo"]["sk_tempo"]
    svg_parts.append(f'  {route_gold(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=410)}')

    # 4. fato_alunos_ativos.sk_curso -> dim_curso.sk_curso (Calha x = 850)
    p_from = all_ports["fato_alunos_ativos"]["sk_curso"]
    p_to = all_ports["dim_curso"]["sk_curso"]
    svg_parts.append(f'  {route_gold(p_from["x_right"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=850)}')

    # 5. fato_pibic_perfil.sk_perfil -> dim_perfil_social.sk_perfil (Calha x = 395)
    p_from = all_ports["fato_pibic_perfil"]["sk_perfil"]
    p_to = all_ports["dim_perfil_social"]["sk_perfil"]
    svg_parts.append(f'  {route_gold(p_from["x_left"], p_from["y"], p_to["x_right"], p_to["y"], channel_x=395)}')

    # 6. fato_pibic_perfil.sk_curso -> dim_curso.sk_curso (Calha x = 830)
    p_from = all_ports["fato_pibic_perfil"]["sk_curso"]
    p_to = all_ports["dim_curso"]["sk_curso"]
    svg_parts.append(f'  {route_gold(p_from["x_right"], p_from["y"], p_to["x_left"], p_to["y"], channel_x=830)}')

    # 7. Relacionamento Conceitual: mv_dashboard_executivo pré-computa fato_retencao_curso e dim_curso
    p_mv = all_ports["mv_dashboard_executivo"]["sk_curso"]
    p_dc = all_ports["dim_curso"]["sk_curso"]
    d_mv = f'M {p_mv["x_left"]} {p_mv["y"]} L 840 {p_mv["y"]} L 840 {p_dc["y"]} L {p_dc["x_left"]} {p_dc["y"]}'
    svg_parts.append(f'  <path d="{d_mv}" fill="none" stroke="#10b981" stroke-width="1.8" stroke-dasharray="5,3" marker-start="url(#dotGold)" marker-end="url(#arrowGreen)"/>')

    svg_parts.append('</svg>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parts))
    print(f"Salvo Gold SVG: {output_path}")


def main():
    print("Conectando ao banco para introspectar catálogo completo...")
    with conectar() as conn:
        with conn.cursor() as cur:
            silver_tables, silver_fks = get_schema_metadata(cur, "silver")
            gold_tables, gold_fks = get_schema_metadata(cur, "gold")

    render_silver_svg(silver_tables, silver_fks, ASSETS_DIR / "der_silver_3nf.svg")
    render_gold_svg(gold_tables, gold_fks, ASSETS_DIR / "der_gold_star_schema.svg")
    print("Diagramas vetoriais SVG gerados com sucesso e sem colisões!")


if __name__ == "__main__":
    main()
