"""
Pipeline de Construção da Camada Gold

Integra discentes, estruturas curriculares e metadados de cursos, mede a taxa de casamento dos
joins e calcula as métricas de retenção, tempo real de conclusão e evasão por curso.

As agregações rodam dentro do PostgreSQL (ELT): as funções gold.calcular_* e a procedure
gold.materializar_gold (db/migrations/0022_gold_sql_nativo.sql) leem as tabelas silver.* e gravam
as gold.* e os relatórios JSON de gold.relatorios. Este script só carrega as regras de
harmonização de cursos (a referência que o SQL usa), dispara a procedure e confere o resultado,
tudo numa transação: o painel nunca lê metade da gold.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_gold")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.tabelas import gravar, tem_linhas  # noqa: E402

# Mapeamento detalhado e auditável de Harmonização Canônica (Entity Resolution)
# Converte nomenclaturas legadas/abreviadas do SIGRA para as matrizes formais da Estrutura Curricular
CANONICAL_RULES_METADATA = [
    {
        "origem_sigra": "PORTUGUES DO BRASIL COMO SEGUNDA LINGUA",
        "destino_estrutura": "LETRAS - PORTUGUES DO BRASIL COMO SEGUNDA LINGUA",
        "categoria": "Letras e Línguas",
        "justificativa": "Habilitação específica do curso de Letras cadastrada com prefixo na matriz curricular.",
    },
    {
        "origem_sigra": "LINGUAGENS",
        "destino_estrutura": "EDUCACAO DO CAMPO - LINGUAGENS, ARTES E LITERATURA",
        "categoria": "Educação do Campo (FUP)",
        "justificativa": "Ênfase da Licenciatura em Educação do Campo da Faculdade de Planaltina.",
    },
    {
        "origem_sigra": "LINGUAGENS, ARTES E LITERATURA",
        "destino_estrutura": "EDUCACAO DO CAMPO - LINGUAGENS, ARTES E LITERATURA",
        "categoria": "Educação do Campo (FUP)",
        "justificativa": "Denominação completa da ênfase de Educação do Campo no campus Planaltina.",
    },
    {
        "origem_sigra": "CIENCIAS DA NATUREZA E MATEMATICA",
        "destino_estrutura": "EDUCACAO DO CAMPO - CIENCIAS DA NATUREZA E MATEMATICA",
        "categoria": "Educação do Campo (FUP)",
        "justificativa": "Ênfase de Ciências da Natureza e Matemática de Educação do Campo.",
    },
    {
        "origem_sigra": "CIENCIAS DA NATUREZA",
        "destino_estrutura": "EDUCACAO DO CAMPO - CIENCIAS DA NATUREZA",
        "categoria": "Educação do Campo (FUP)",
        "justificativa": "Matriz de Ciências da Natureza de Educação do Campo da FUP.",
    },
    {
        "origem_sigra": "PROGRAMACAO VISUAL",
        "destino_estrutura": "DESIGN - PROGRAMACAO VISUAL",
        "categoria": "Design / Desenho Industrial",
        "justificativa": "Habilitação clássica de Design vinculada à matriz oficial de Programação Visual.",
    },
    {
        "origem_sigra": "PROJETO DO PRODUTO",
        "destino_estrutura": "DESIGN - PROJETO DO PRODUTO",
        "categoria": "Design / Desenho Industrial",
        "justificativa": "Habilitação clássica de Design vinculada à matriz oficial de Projeto do Produto.",
    },
    {
        "origem_sigra": "PROJETO DE PRODUTO",
        "destino_estrutura": "DESIGN - PROJETO DO PRODUTO",
        "categoria": "Design / Desenho Industrial",
        "justificativa": "Variação de preposição 'DE'/'DO' unificada para a matriz oficial.",
    },
    {
        "origem_sigra": "LINGUA DE SINAIS BRASILEIRA - PORTUGUES COMO SEGUNDA LINGUA",
        "destino_estrutura": "LINGUA DE SINAIS BRASILEIRA -PORTUGUES COMO SEGUNDA LINGUA",
        "categoria": "Correção de Typo no Portal",
        "justificativa": "A matriz no portal dados.unb.br foi cadastrada com ausência de espaço após o hífen ('-PORTUGUES').",
    },
    {
        "origem_sigra": "PEDAGOGIA - 1A LICENCIATURA",
        "destino_estrutura": "PEDAGOGIA",
        "categoria": "Licenciatura",
        "justificativa": "Programa de 1ª Licenciatura vinculado à matriz de referência de Pedagogia.",
    },
    {
        "origem_sigra": "COMPOSICAO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "MATEMATICA - SEGUNDA LICENCIATURA",
        "destino_estrutura": "MATEMATICA",
        "categoria": "Licenciatura",
        "justificativa": "Programa especial de 2ª Licenciatura vinculado à matriz de referência de Matemática.",
    },
    {
        "origem_sigra": "CIENCIAS NATURAIS - SEGUNDA LICENCIATURA",
        "destino_estrutura": "CIENCIAS NATURAIS",
        "categoria": "Licenciatura",
        "justificativa": "Programa especial de 2ª Licenciatura vinculado à matriz de referência de Ciências Naturais.",
    },
    {
        "origem_sigra": "ADMINISTRACAO DE EMPRESAS",
        "destino_estrutura": "ADMINISTRACAO",
        "categoria": "Habilitação Legada",
        "justificativa": "Nomenclatura antiga no SIGRA vinculada à matriz vigente de Administração.",
    },
    {
        "origem_sigra": "ENFERMAGEM E OBSTETRICIA",
        "destino_estrutura": "ENFERMAGEM",
        "categoria": "Habilitação Legada",
        "justificativa": "Nomenclatura antiga no SIGRA vinculada à matriz vigente de Enfermagem.",
    },
    {
        "origem_sigra": "VIOLAO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "SAXOFONE",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "VIOLINO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "CANTO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "PIANO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "REGENCIA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "CONTRABAIXO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "TROMBONE",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "TROMPETE",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "VIOLA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "VIOLONCELO",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "OBOE",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "FAGOTE",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "FLAUTA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "CLARINETA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental isolada tem poucos discentes para análise própria (k pequeno); agregada ao curso-tronco de Música.",
    },
    {
        "origem_sigra": "TROMPA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Habilitação instrumental sem matriz específica cadastrada, alocada na matriz geral de Música.",
    },
    {
        "origem_sigra": "LINGUA PORTUGUESA E RESPECTIVA LITERATURA",
        "destino_estrutura": "LETRAS - LINGUA PORTUGUESA E RESPECTIVA LITERATURA",
        "categoria": "Letras e Línguas",
        "justificativa": "Prefixo formal 'LETRAS' adicionado pela matriz curricular.",
    },
    {
        "origem_sigra": "CONTROLE E AUTOMACAO",
        "destino_estrutura": "ENGENHARIA MECATRONICA - CONTROLE E AUTOMACAO",
        "categoria": "Engenharias",
        "justificativa": "Matriz formal com prefixo de Engenharia Mecatrônica.",
    },
    {
        "origem_sigra": "LINGUA INGLESA E RESPECTIVA LITERATURA",
        "destino_estrutura": "LETRAS - LINGUA INGLESA E RESPECTIVA LITERATURA",
        "categoria": "Letras e Línguas",
        "justificativa": "Prefixo formal 'LETRAS' adicionado pela matriz curricular.",
    },
    {
        "origem_sigra": "LINGUA ESPANHOLA E LITERATURA ESPANHOLA E HISPANO-AMERICANA",
        "destino_estrutura": "LETRAS - LINGUA ESPANHOLA E LITERATURA ESPANHOLA E HISPANO-AMERICANA",
        "categoria": "Letras e Línguas",
        "justificativa": "Prefixo formal 'LETRAS' adicionado pela matriz curricular.",
    },
    {
        "origem_sigra": "ESPANHOL",
        "destino_estrutura": "LETRAS - LINGUA ESPANHOLA E LITERATURA ESPANHOLA E HISPANO-AMERICANA",
        "categoria": "Letras e Línguas",
        "justificativa": "Abreviação coloquial do SIGRA mapeada para a matriz curricular oficial.",
    },
    {
        "origem_sigra": "LINGUA FRANCESA E RESPECTIVA LITERATURA",
        "destino_estrutura": "LETRAS - LINGUA FRANCESA E RESPECTIVA LITERATURA",
        "categoria": "Letras e Línguas",
        "justificativa": "Prefixo formal 'LETRAS' adicionado pela matriz curricular.",
    },
    {
        "origem_sigra": "FRANCES",
        "destino_estrutura": "LETRAS - LINGUA FRANCESA E RESPECTIVA LITERATURA",
        "categoria": "Letras e Línguas",
        "justificativa": "Abreviação coloquial do SIGRA mapeada para a matriz curricular oficial.",
    },
    {
        "origem_sigra": "INGLES",
        "destino_estrutura": "LETRAS - LINGUA INGLESA E RESPECTIVA LITERATURA",
        "categoria": "Letras e Línguas",
        "justificativa": "Abreviação coloquial do SIGRA mapeada para a matriz curricular oficial.",
    },
    {
        "origem_sigra": "LINGUA E LITERATURA JAPONESA",
        "destino_estrutura": "LETRAS - LINGUA E LITERATURA JAPONESA",
        "categoria": "Letras e Línguas",
        "justificativa": "Prefixo formal 'LETRAS' adicionado pela matriz curricular.",
    },
    {
        "origem_sigra": "ADMINISTRACAO PUBLICA",
        "destino_estrutura": "ADMINISTRACAO",
        "categoria": "Administração",
        "justificativa": "Ênfase pública vinculada à matriz curricular de Administração.",
    },
    {
        "origem_sigra": "FARMACIA CLINICA E INDUSTRIAL",
        "destino_estrutura": "FARMACIA",
        "categoria": "Saúde",
        "justificativa": "Habilitação clínica e industrial vinculada à matriz de Farmácia.",
    },
    {
        "origem_sigra": "INTERPRETACAO TEATRAL",
        "destino_estrutura": "ARTES CENICAS",
        "categoria": "Artes",
        "justificativa": "Habilitação de Interpretação Teatral vinculada à matriz de Artes Cênicas.",
    },
    {
        "origem_sigra": "LICENCIATURA EM ARTES VISUAIS",
        "destino_estrutura": "ARTES VISUAIS",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Artes Visuais.",
    },
    {
        "origem_sigra": "LICENCIATURA EM CIENCIAS BIOLOGICAS",
        "destino_estrutura": "CIENCIAS BIOLOGICAS",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Ciências Biológicas.",
    },
    {
        "origem_sigra": "LICENCIATURA EM COMPUTACAO",
        "destino_estrutura": "COMPUTACAO",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Computação.",
    },
    {
        "origem_sigra": "LICENCIATURA EM FISICA",
        "destino_estrutura": "FISICA",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Física.",
    },
    {
        "origem_sigra": "LICENCIATURA EM MATEMATICA",
        "destino_estrutura": "MATEMATICA",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Matemática.",
    },
    {
        "origem_sigra": "LICENCIATURA EM QUIMICA",
        "destino_estrutura": "QUIMICA",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura vinculada à matriz correspondente de Química.",
    },
    {
        "origem_sigra": "LICENCIATURA EM TEATRO",
        "destino_estrutura": "ARTES CENICAS",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura em Teatro vinculada à matriz de Artes Cênicas.",
    },
    {
        "origem_sigra": "LICENCIATURA EM MUSICA",
        "destino_estrutura": "MUSICA",
        "categoria": "Licenciatura",
        "justificativa": "Licenciatura em Música vinculada à matriz de Música.",
    },
    {
        "origem_sigra": "HABILITACAO TRADUCAO - INGLES",
        "destino_estrutura": "LETRAS - TRADUCAO - INGLES",
        "categoria": "Letras e Línguas",
        "justificativa": "Habilitação em Tradução com prefixo de Letras.",
    },
    {
        "origem_sigra": "HABILITACAO TRADUCAO - FRANCES",
        "destino_estrutura": "LETRAS - TRADUCAO - FRANCES",
        "categoria": "Letras e Línguas",
        "justificativa": "Habilitação em Tradução com prefixo de Letras.",
    },
    {
        "origem_sigra": "HABILITACAO TRADUCAO - ESPANHOL",
        "destino_estrutura": "LETRAS - TRADUCAO - ESPANHOL",
        "categoria": "Letras e Línguas",
        "justificativa": "Habilitação em Tradução com prefixo de Letras.",
    },
    # Variações de nomenclatura observadas no campo "unidade" da base de bolsistas de
    # Iniciação Científica (PIBIC/PIVIC), que usa abreviações e formatações distintas do SIGRA.
    {
        "origem_sigra": "LETRAS-TRADUCAO ESPANHOL",
        "destino_estrutura": "LETRAS - TRADUCAO - ESPANHOL",
        "categoria": "Letras e Línguas",
        "justificativa": "Abreviação sem espaços usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "TRADUCAO - FRANCES",
        "destino_estrutura": "LETRAS - TRADUCAO - FRANCES",
        "categoria": "Letras e Línguas",
        "justificativa": "Nomenclatura sem prefixo 'LETRAS' usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "LETRAS TRADUCAO - FRANCES",
        "destino_estrutura": "LETRAS - TRADUCAO - FRANCES",
        "categoria": "Letras e Línguas",
        "justificativa": "Nomenclatura sem hífen após 'LETRAS' usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "TRADUCAO-INGLES",
        "destino_estrutura": "LETRAS - TRADUCAO - INGLES",
        "categoria": "Letras e Línguas",
        "justificativa": "Abreviação sem espaços usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "LINGUA DE SINAIS BRASILEIRA/PORTUGUES COMO SEGUNDA LINGUA",
        "destino_estrutura": "LINGUA DE SINAIS BRASILEIRA -PORTUGUES COMO SEGUNDA LINGUA",
        "categoria": "Correção de Typo no Portal",
        "justificativa": "Variante com barra em vez de hífen, usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "EDUCACAO DO CAMPO - LINGUAGENS",
        "destino_estrutura": "EDUCACAO DO CAMPO - LINGUAGENS, ARTES E LITERATURA",
        "categoria": "Educação do Campo (FUP)",
        "justificativa": "Nome abreviado da ênfase, usado no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "MUSICA: LICENCIATURA",
        "destino_estrutura": "MUSICA",
        "categoria": "Música e Instrumentos",
        "justificativa": "Nomenclatura usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "BIOLOGIA",
        "destino_estrutura": "CIENCIAS BIOLOGICAS",
        "categoria": "Habilitação Legada",
        "justificativa": "Nome coloquial usado no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "PSICOLOGIA-PSICOLOGO",
        "destino_estrutura": "PSICOLOGIA",
        "categoria": "Habilitação Legada",
        "justificativa": "Sufixo de titulação concatenado ao nome, usado no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "ENGENHARIA DE CONTROLE E AUTOMACAO",
        "destino_estrutura": "ENGENHARIA MECATRONICA - CONTROLE E AUTOMACAO",
        "categoria": "Engenharias",
        "justificativa": "Nomenclatura alternativa usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "DAP / COMUNICACAO SOCIAL - AUDIOVISUAL",
        "destino_estrutura": "AUDIOVISUAL",
        "categoria": "Comunicação",
        "justificativa": "Sigla do departamento (DAP) remanescente da extração do campo 'unidade' do PIBIC.",
    },
    {
        "origem_sigra": "CIENCIAS BIOLOGICAS / DEPARTAMENTO DE ZOOLOGIA",
        "destino_estrutura": "CIENCIAS BIOLOGICAS",
        "categoria": "Habilitação Legada",
        "justificativa": "Subunidade de pesquisa remanescente da extração do campo 'unidade' do PIBIC.",
    },
    {
        "origem_sigra": "JOR / JORNALISMO",
        "destino_estrutura": "JORNALISMO",
        "categoria": "Comunicação",
        "justificativa": "Sigla do departamento (JOR) remanescente da extração do campo 'unidade' do PIBIC.",
    },
    {
        "origem_sigra": "GRADUACAO EM CIENCIA POLITICA",
        "destino_estrutura": "CIENCIA POLITICA",
        "categoria": "Ciências Sociais",
        "justificativa": "Variação verbosa do campo 'unidade' usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "GRADUACAO EM ARQUITETURA E URBANISMO",
        "destino_estrutura": "ARQUITETURA E URBANISMO",
        "categoria": "Habilitação Legada",
        "justificativa": "Variação verbosa do campo 'unidade' usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "ARQUITETURA E URBANISMO / FACULDADE DE ARQUITETURA E URBANISMO",
        "destino_estrutura": "ARQUITETURA E URBANISMO",
        "categoria": "Habilitação Legada",
        "justificativa": "Nome da faculdade remanescente da extração do campo 'unidade' do PIBIC.",
    },
    {
        "origem_sigra": "GRADUACAO DE MEDICINA",
        "destino_estrutura": "MEDICINA",
        "categoria": "Habilitação Legada",
        "justificativa": "Variação verbosa do campo 'unidade' usada no cadastro de bolsistas de IC (PIBIC).",
    },
    {
        "origem_sigra": "INSTITUTO DE CIENCIAS BIOLOGICAS / BIOTECNOLOGIA",
        "destino_estrutura": "CIENCIAS BIOLOGICAS",
        "categoria": "Habilitação Legada",
        "justificativa": "UnB não oferece graduação própria em Biotecnologia; subárea de pesquisa do Instituto de Ciências Biológicas, alocada no curso de Ciências Biológicas.",
    },
]

# Dicionário dinâmico de mapeamento rápido
COURSE_ALIASES = {rule["origem_sigra"]: rule["destino_estrutura"]
                  for rule in CANONICAL_RULES_METADATA}

# Cursos-tronco de ingresso comum (ex.: Engenharia na FGA/FT), onde o discente ainda não
# escolheu a habilitação terminal. Permanecem na tabela Gold (compõem o panorama geral da
# UnB), mas são descartados pelo dashboard nas telas de Visão Executiva e Detalhe por Curso,
# que exigem um curso terminal para o raio-x individual — ver uso em src/dashboard/app.py.
# Educação Física - Ciclo Básico é a Área Básica de Ingresso (ABI) da FEF: quatro semestres
# comuns e depois a escolha entre bacharelado e licenciatura. Ninguém se forma nela.
EXCLUDED_GENERIC_COURSES = {"ENGENHARIA", "EDUCACAO FISICA - CICLO BASICO"}

# Limiares do benchmark com o Censo da Educação Superior (INEP). Em cursos com poucas
# matrículas um único aluno desloca a taxa em vários pontos percentuais, e comparar contra
# meia dúzia de instituições não caracteriza um padrão nacional do curso.
MIN_MATRICULAS_BENCHMARK = 50
MIN_IES_BENCHMARK = 10

# As taxas por curso só usam coortes que já tiveram tempo de concluir: ingresso até
# (último ano de ingresso na base - ANOS_MATURACAO_COORTE). Coortes recentes, ainda quase
# todas ativas, derrubariam artificialmente a formatura e a evasão. Com 6 anos a coorte de
# 2018 ainda tinha 34% de ativos no extrato de 07/2024; com 8 anos a mais recente fica com 9%.
ANOS_MATURACAO_COORTE = 8


TABELAS_GOLD = (
    "gold.regras_harmonizacao_canonicas",
    "gold.ativos_hoje_cursos_unb",
    "gold.retencao_cursos_unb",
    "gold.inep_benchmark_cursos_unb",
    "gold.pibic_social_unb",
)


def valor_bolsa_ic_vigente() -> float:
    """Valor mensal da bolsa de IC na coleta mais recente da tabela do CNPq (simulador do painel)."""
    caminho = BASE_DIR / "data" / "bronze" / "cnpq_valor_bolsa_ic.json"
    vigencias: List[Dict] = json.loads(caminho.read_text(encoding="utf-8"))["vigencias"]
    return float(max(vigencias, key=lambda v: v["vigente_desde"])["valor_mensal"])


def build_gold_layer() -> None:
    """Carrega as regras de harmonização e materializa a gold no banco, numa transação só."""
    regras = pd.DataFrame(CANONICAL_RULES_METADATA).assign(discentes_impactados=0)
    # A contagem de vínculos por regra é calculada pela procedure; o pipeline só entrega a referência.
    valor_bolsa = valor_bolsa_ic_vigente() if tem_linhas("silver.pibic_bolsistas") else None

    with conectar(autocommit=True) as conn:
        conn.add_notice_handler(lambda aviso: logger.info(aviso.message_primary))
        with conn.transaction():
            gravar(regras, "gold.regras_harmonizacao_canonicas", conn=conn)
            conn.execute(
                "CALL gold.materializar_gold(%s::integer, %s::text[], %s::integer, %s::numeric)",
                (ANOS_MATURACAO_COORTE, sorted(EXCLUDED_GENERIC_COURSES), MIN_MATRICULAS_BENCHMARK, valor_bolsa),
            )
        for tabela in TABELAS_GOLD:
            conn.execute(f"ANALYZE {tabela}")
        comparaveis = conn.execute(
            "SELECT count(*) FROM gold.inep_benchmark_cursos_unb WHERE n_ies_comparadas >= %s", (MIN_IES_BENCHMARK,)
        ).fetchone()[0]
    logger.info(f"Benchmark INEP: {comparaveis} cursos com pelo menos {MIN_IES_BENCHMARK} federais comparáveis.")


if __name__ == "__main__":
    build_gold_layer()
