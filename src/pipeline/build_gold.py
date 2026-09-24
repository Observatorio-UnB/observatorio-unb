"""
Pipeline de Construção da Camada Gold
Realiza a integração heterogênea entre discentes, estruturas curriculares e metadados de cursos.
Mede a taxa de casamento de joins e calcula as métricas consolidadas de retenção,
tempo real de conclusão e taxas de evasão por curso.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_gold")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SILVER_DIR = BASE_DIR / "data" / "silver"
GOLD_DIR = BASE_DIR / "data" / "gold"

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
        "origem_sigra": "JORNALISMO",
        "destino_estrutura": "COMUNICACAO SOCIAL - JORNALISMO",
        "categoria": "Comunicação",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco (nome padronizado com o prefixo do catálogo oficial).",
    },
    {
        "origem_sigra": "COMUNICACAO ORGANIZACIONAL",
        "destino_estrutura": "COMUNICACAO SOCIAL - COMUNICACAO ORGANIZACIONAL",
        "categoria": "Comunicação",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco.",
    },
    {
        "origem_sigra": "PUBLICIDADE E PROPAGANDA",
        "destino_estrutura": "COMUNICACAO SOCIAL - PUBLICIDADE E PROPAGANDA",
        "categoria": "Comunicação",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco.",
    },
    {
        "origem_sigra": "AUDIOVISUAL",
        "destino_estrutura": "COMUNICACAO SOCIAL - AUDIOVISUAL",
        "categoria": "Comunicação",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco.",
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
        "origem_sigra": "SOCIOLOGIA",
        "destino_estrutura": "CIENCIAS SOCIAIS - SOCIOLOGIA",
        "categoria": "Ciências Sociais",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco.",
    },
    {
        "origem_sigra": "ANTROPOLOGIA",
        "destino_estrutura": "CIENCIAS SOCIAIS - ANTROPOLOGIA",
        "categoria": "Ciências Sociais",
        "justificativa": "Habilitação com matriz própria e volume suficiente de discentes; mantida desagregada da matriz tronco.",
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
        "destino_estrutura": "COMUNICACAO SOCIAL - AUDIOVISUAL",
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
        "destino_estrutura": "COMUNICACAO SOCIAL - JORNALISMO",
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
COURSE_ALIASES = {rule["origem_sigra"]: rule["destino_estrutura"] for rule in CANONICAL_RULES_METADATA}

# Cursos-tronco de ingresso comum (ex.: Engenharia na FGA/FT), onde o discente ainda não
# escolheu a habilitação terminal. Permanecem na tabela Gold (compõem o panorama geral da
# UnB), mas são descartados pelo dashboard nas telas de Visão Executiva e Detalhe por Curso,
# que exigem um curso terminal para o raio-x individual — ver uso em src/dashboard/app.py.
EXCLUDED_GENERIC_COURSES = {"ENGENHARIA"}

# Limiares do benchmark com o Censo da Educação Superior (INEP). Em cursos com poucas
# matrículas um único aluno desloca a taxa em vários pontos percentuais, e comparar contra
# meia dúzia de instituições não caracteriza um padrão nacional do curso.
MIN_MATRICULAS_BENCHMARK = 50
MIN_IES_BENCHMARK = 10


def normalize_turno_grupo(turno_norm: str) -> str:
    """Unifica matutino/vespertino em Diurno; preserva Noturno e Integral."""
    valor = turno_norm or ""
    if "NOTURNO" in valor:
        return "NOTURNO"
    if "INTEGRAL" in valor:
        return "INTEGRAL"
    return "DIURNO"


def normalize_categoria_grau(grau_norm: str) -> str:
    """Agrupa a titulação conferida em Bacharelado ou Licenciatura para fins de análise."""
    valor = grau_norm or ""
    if "LICENCIAD" in valor:
        return "LICENCIATURA"
    return "BACHARELADO"


def normalize_campus_nome(campus_raw: str) -> str:
    """Unifica os nomes de campus entre as bases SIGRA e PIBIC (grafias distintas na origem).

    FGA e FCE são renomeadas para suas denominações institucionais atuais
    (Faculdade de Ciências e Tecnologias em Engenharia / em Saúde); Darcy Ribeiro
    e Planaltina (FUP) mantêm a mesma identidade, apenas com grafia padronizada.
    """
    valor = campus_raw or ""
    if "GAMA" in valor:
        return "FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)"
    if "CEILANDIA" in valor:
        return "FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)"
    if "PLANALTINA" in valor:
        return "FACULDADE DE PLANALTINA (FUP)"
    return "DARCY RIBEIRO"


def build_area_por_curso(df_cur: pd.DataFrame, cursos_canonicos) -> Dict[str, str]:
    """Mapa nome_curso_norm -> Grande Área oficial (CNPq/MEC), a partir do catálogo de cursos.

    Cursos-tronco sem entrada própria no catálogo (ex.: "COMUNICACAO SOCIAL", cujas
    habilitações — Jornalismo, Publicidade e Propaganda, Audiovisual etc. — são cadastradas
    separadamente) herdam a área de suas habilitações, quando todas concordam na mesma
    Grande Área. Compartilhado entre a tabela de retenção (SIGRA) e a de PIBIC.
    """
    area_por_curso = (
        df_cur.dropna(subset=["area_conhecimento_norm"])
        .groupby("nome_curso_norm")["area_conhecimento_norm"]
        .agg(lambda s: s.mode().iloc[0])
    )
    area_dict = area_por_curso.to_dict()
    for nome_base in cursos_canonicos:
        if not nome_base or nome_base in area_dict:
            continue
        candidatas = area_por_curso[area_por_curso.index.str.startswith(f"{nome_base} - ")]
        if not candidatas.empty and candidatas.nunique() == 1:
            area_dict[nome_base] = candidatas.iloc[0]
    return area_dict


def build_gold_layer() -> Tuple[pd.DataFrame, Dict]:
    """Executa o merge heterogêneo e a agregação analítica da camada Gold."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Carregar datasets da camada Silver
    sig_path = SILVER_DIR / "sigra_graduacao_silver.csv"
    est_path = SILVER_DIR / "estrutura_curricular_silver.csv"
    cur_path = SILVER_DIR / "cursos_graduacao_silver.csv"
    
    df_sig = pd.read_csv(sig_path)
    df_est = pd.read_csv(est_path)
    df_cur = pd.read_csv(cur_path)

    total_discentes = len(df_sig)

    # 2. Aplicar mapeamento canônico de cursos
    df_sig["curso_canonico"] = df_sig["curso_norm"].replace(COURSE_ALIASES)

    # 2.1 Cursos com oferta dupla: o mesmo nome de curso no catálogo (cursos_graduacao_silver)
    # tem entradas tanto de Bacharelado quanto de Licenciatura (ex.: Química, Física, Letras).
    # O catálogo não traz uma chave que ligue o código de "opcao" do SIGRA ao grau conferido, e
    # essa correspondência não foi encontrada em nenhuma fonte pública (ver docs/dicionario_dados_gold.md).
    # Em vez de arriscar uma separação por aluno não verificável — o que pode atribuir discentes
    # ao grau errado, como visto quando o menor código de opção de Física isolou um subgrupo
    # minoritário sem nenhum formado —, esses cursos são mantidos como uma única linha na Gold,
    # com o grau explicitamente marcado como "MISTO" em vez de assumir Bacharelado ou Licenciatura.
    df_cur["categoria_grau"] = df_cur["grau_academico_norm"].apply(normalize_categoria_grau)
    mixed_courses = set(
        df_cur.groupby("nome_curso_norm")["categoria_grau"].nunique().loc[lambda s: s > 1].index
    )

    # 3. Join com Estrutura Curricular
    df_merged = pd.merge(
        df_sig,
        df_est,
        left_on="curso_canonico",
        right_on="nome_curso_norm",
        how="left",
        suffixes=("", "_est"),
    )

    # 4. Join com Cursos de Graduação (metadados de campus, turno e unidade)
    # Deduplica catálogo de cursos por nome canônico
    cur_dedup = df_cur.groupby("nome_curso_norm", as_index=False).first()
    df_merged = pd.merge(
        df_merged,
        cur_dedup[["nome_curso_norm", "turno_norm", "campus_norm", "grau_academico_norm", "area_conhecimento_norm", "unidade_responsavel_norm"]],
        left_on="curso_canonico",
        right_on="nome_curso_norm",
        how="left",
    )
    # Cursos-tronco (ex.: "COMUNICACAO SOCIAL") não têm entrada própria no catálogo e
    # ficam sem área após o merge acima — completa com a área herdada das habilitações.
    area_lookup = build_area_por_curso(df_cur, df_sig["curso_canonico"].unique())
    df_merged["area_conhecimento_norm"] = df_merged["area_conhecimento_norm"].fillna(
        df_merged["curso_canonico"].map(area_lookup)
    )

    # 5. Auditoria da Taxa de Casamento (Join Match Rate) e Governança de Entidades
    matched_mask = df_merged["semestre_conclusao_ideal"].notna()
    matched_count = int(matched_mask.sum())
    unmatched_count = total_discentes - matched_count
    match_rate_pct = (matched_count / total_discentes) * 100
    
    unmatched_courses = (
        df_merged[~matched_mask]["curso_norm"]
        .value_counts()
        .head(10)
        .to_dict()
    )
    
    # Contagem de alunos impactados por cada regra de harmonização canônica
    orig_counts = df_sig["curso_norm"].value_counts().to_dict()
    regras_auditadas = []
    total_discentes_harmonizados = 0
    for rule in CANONICAL_RULES_METADATA:
        orig = rule["origem_sigra"]
        cnt = orig_counts.get(orig, 0)
        total_discentes_harmonizados += cnt
        regras_auditadas.append({
            "origem_sigra": orig,
            "destino_estrutura": rule["destino_estrutura"],
            "categoria": rule["categoria"],
            "justificativa": rule["justificativa"],
            "discentes_impactados": cnt,
        })
    regras_auditadas.sort(key=lambda r: r["discentes_impactados"], reverse=True)

    with open(GOLD_DIR / "regras_harmonizacao_canonicas.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_regras": len(regras_auditadas),
            "total_discentes_harmonizados": total_discentes_harmonizados,
            "metodologia": "Entity Resolution e Harmonização Canônica (SIGRA -> Matrizes Curriculares Ativas)",
            "regras": regras_auditadas,
        }, f, indent=2, ensure_ascii=False)

    join_report = {
        "total_discentes_graduacao": total_discentes,
        "discentes_com_estrutura_casada": matched_count,
        "discentes_sem_casamento": unmatched_count,
        "taxa_de_casamento_pct": round(match_rate_pct, 2),
        "cursos_nao_casados_principais": unmatched_courses,
        "harmonizacao_ativa": True,
        "total_discentes_harmonizados": total_discentes_harmonizados,
        "justificativa_descartes": (
            "Taxa de 100.00% alcançada através de Harmonização Canônica transparente "
            "e auditável de regras de equivalência entre sistemas legados (SIGRA) e matrizes curriculares ativas. "
            "Zero registros descartados."
        ) if unmatched_count == 0 else (
            f"{unmatched_count} registros não casados restantes."
        ),
    }
    
    with open(GOLD_DIR / "relatorio_casamento_joins.json", "w", encoding="utf-8") as f:
        json.dump(join_report, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Taxa de Casamento dos Joins: {match_rate_pct:.2f}% ({matched_count:,}/{total_discentes:,} discentes)")

    # 6. Cálculo de Indicadores no Nível Individual
    # Cursos-tronco de ingresso comum (ex.: Engenharia genérica) permanecem na tabela e nas
    # métricas globais; são descartados apenas nas telas de Visão Executiva e Detalhe por Curso
    # do dashboard (ver EXCLUDED_GENERIC_COURSES em src/dashboard/app.py), pois não são cursos
    # terminais válidos para um raio-x individual, mas ainda compõem o panorama geral da UnB.
    df_valid = df_merged[matched_mask].copy()

    is_formado = df_valid["tipo_saida_grupo"] == "FORMATURA"
    df_valid["is_formado"] = is_formado
    df_valid["is_evadido"] = df_valid["tipo_saida_grupo"] == "EVASAO_DESLIGAMENTO"
    df_valid["is_mudanca_interna"] = df_valid["tipo_saida_grupo"] == "MUDANCA_INTERNA"
    
    # Comparações de tempo para formados
    df_valid["formou_tempo_minimo"] = np.where(
        is_formado,
        df_valid["semestres_permanencia_valida"] <= df_valid["semestre_conclusao_minimo"],
        False,
    )
    df_valid["formou_tempo_ideal"] = np.where(
        is_formado,
        df_valid["semestres_permanencia_valida"] <= df_valid["semestre_conclusao_ideal"],
        False,
    )
    df_valid["formou_acima_ideal"] = np.where(
        is_formado,
        df_valid["semestres_permanencia_valida"] > df_valid["semestre_conclusao_ideal"],
        False,
    )
    df_valid["formou_limite_maximo"] = np.where(
        is_formado,
        df_valid["semestres_permanencia_valida"] >= df_valid["semestre_conclusao_maximo"],
        False,
    )
    df_valid["desvio_semestres_individual"] = np.where(
        is_formado,
        df_valid["semestres_permanencia_valida"] - df_valid["semestre_conclusao_ideal"],
        np.nan,
    )

    # 7. Agregação Analítica por Curso
    course_groups = df_valid.groupby("curso_canonico")
    
    gold_rows = []
    for curso, grp in course_groups:
        total_ing = len(grp)
        # Supressão ética de grupos muito pequenos (< 5 discentes)
        if total_ing < 5:
            continue
            
        grp_formados = grp[grp["is_formado"]]
        n_formados = len(grp_formados)
        n_evadidos = grp["is_evadido"].sum()
        n_mudanca = grp["is_mudanca_interna"].sum()
        
        taxa_formatura = (n_formados / total_ing * 100) if total_ing else 0.0
        taxa_evasao = (n_evadidos / total_ing * 100) if total_ing else 0.0
        
        if n_formados > 0:
            pct_minimo = (grp_formados["formou_tempo_minimo"].sum() / n_formados) * 100
            pct_ideal = (grp_formados["formou_tempo_ideal"].sum() / n_formados) * 100
            pct_acima = (grp_formados["formou_acima_ideal"].sum() / n_formados) * 100
            pct_maximo = (grp_formados["formou_limite_maximo"].sum() / n_formados) * 100
            
            tempo_medio = grp_formados["semestres_permanencia_valida"].mean()
            tempo_mediano = grp_formados["semestres_permanencia_valida"].median()
            desvio_medio = grp_formados["desvio_semestres_individual"].mean()
        else:
            pct_minimo = pct_ideal = pct_acima = pct_maximo = 0.0
            tempo_medio = tempo_mediano = desvio_medio = np.nan
            
        # Prazos regulamentares da estrutura
        sem_min = grp["semestre_conclusao_minimo"].iloc[0]
        sem_ideal = grp["semestre_conclusao_ideal"].iloc[0]
        sem_max = grp["semestre_conclusao_maximo"].iloc[0]
        ch_total = grp["ch_total_minima"].iloc[0]
        
        # Metadados
        campus_raw = grp["campus_norm"].dropna().iloc[0] if grp["campus_norm"].notna().any() else "DARCY RIBEIRO"
        campus = normalize_campus_nome(campus_raw)
        turno_raw = grp["turno_norm"].dropna().iloc[0] if grp["turno_norm"].notna().any() else "DIURNO"
        turno = normalize_turno_grupo(turno_raw)
        area = grp["area_conhecimento_norm"].dropna().iloc[0] if grp["area_conhecimento_norm"].notna().any() else "OUTRA"
        grau_raw = grp["grau_academico_norm"].dropna().iloc[0] if grp["grau_academico_norm"].notna().any() else "BACHAREL"
        categoria_grau = normalize_categoria_grau(grau_raw)
        if curso in mixed_courses:
            # Curso com Bacharelado e Licenciatura sob o mesmo nome, mas sem forma confiável de
            # separar os discentes (ver comentário 2.1) — não assume um grau único arbitrário.
            grau_raw = "MISTO (BACHARELADO + LICENCIATURA)"
            categoria_grau = "MISTO"
        depto = grp["departamento_norm"].dropna().iloc[0] if grp["departamento_norm"].notna().any() else "UNB"

        gold_rows.append({
            "curso": curso,
            "departamento": depto,
            "campus": campus,
            "turno": turno,
            "area_conhecimento": area,
            "grau_academico": grau_raw,
            "categoria_grau": categoria_grau,
            "semestre_minimo_previsto": sem_min,
            "semestre_ideal_previsto": sem_ideal,
            "semestre_maximo_previsto": sem_max,
            "carga_horaria_minima": ch_total,
            "total_discentes_registrados": total_ing,
            "total_formados": n_formados,
            "total_evadidos_desligados": n_evadidos,
            "taxa_formatura_pct": round(taxa_formatura, 2),
            "taxa_evasao_pct": round(taxa_evasao, 2),
            "formados_tempo_minimo_pct": round(pct_minimo, 2),
            "formados_tempo_ideal_pct": round(pct_ideal, 2),
            "formados_acima_ideal_pct": round(pct_acima, 2),
            "formados_limite_maximo_pct": round(pct_maximo, 2),
            "tempo_medio_real_semestres": round(tempo_medio, 2) if pd.notna(tempo_medio) else np.nan,
            "tempo_mediano_real_semestres": round(tempo_mediano, 2) if pd.notna(tempo_mediano) else np.nan,
            "desvio_medio_semestres": round(desvio_medio, 2) if pd.notna(desvio_medio) else np.nan,
        })
        
    df_gold = pd.DataFrame(gold_rows)
    
    # 8. Cálculo do Índice de Retenção Crítica (IRC) e Classificação de Dificuldade
    # IRC combina atraso médio (desvio) e taxa de evasão.
    desv_clean = df_gold["desvio_medio_semestres"].fillna(0).clip(lower=0)
    evas_clean = df_gold["taxa_evasao_pct"].fillna(0)

    # Normalização min-max robusta: satura nos percentis 5/95 antes de normalizar, para que um
    # único curso outlier (ex.: Engenharia com 74% de evasão) não comprima a escala dos demais.
    def norm_robusto(serie: pd.Series) -> pd.Series:
        p05, p95 = serie.quantile(0.05), serie.quantile(0.95)
        serie_sat = serie.clip(lower=p05, upper=p95)
        return (serie_sat - serie_sat.min()) / (serie_sat.max() - serie_sat.min() + 1e-6)

    norm_desv = norm_robusto(desv_clean)
    norm_evas = norm_robusto(evas_clean)

    # Score ponderado: evasão pesa mais que atraso — perder o aluno (evasão) é mais grave para o
    # DEG do que ele se formar mais devagar (atraso), que ainda é uma conclusão bem-sucedida.
    df_gold["indice_retencao_critica"] = (0.3 * norm_desv + 0.7 * norm_evas) * 100
    df_gold["indice_retencao_critica"] = df_gold["indice_retencao_critica"].round(1)
    
    # Classificação em quartis
    q75 = df_gold["indice_retencao_critica"].quantile(0.75)
    q50 = df_gold["indice_retencao_critica"].quantile(0.50)
    q25 = df_gold["indice_retencao_critica"].quantile(0.25)
    
    def classificar(score):
        if score >= q75:
            return "RETENÇÃO CRÍTICA"
        elif score >= q50:
            return "RETENÇÃO ALTA"
        elif score >= q25:
            return "RETENÇÃO MÉDIA"
        return "RETENÇÃO BAIXA"
        
    df_gold["classificacao_retencao"] = df_gold["indice_retencao_critica"].apply(classificar)
    
    # Enriquecimento com dados do PIBIC (Iniciação Científica) se disponível
    pibic_silver_path = SILVER_DIR / "pibic_bolsistas_silver.csv"
    if pibic_silver_path.exists():
        df_pibic_raw = pd.read_csv(pibic_silver_path)
        # Canonicaliza antes de agregar, para não perder projetos por causa de grafias
        # inconsistentes no campo "unidade" de origem (ver comentário em build_pibic_gold).
        df_pibic_raw["curso_pibic_norm"] = df_pibic_raw["curso_pibic_norm"].replace(COURSE_ALIASES)
        pibic_course_agg = df_pibic_raw.groupby("curso_pibic_norm").agg(
            pibic_total_projetos=("ano", "count"),
            pibic_bolsas_remuneradas=("tipo_bolsa_norm", lambda s: (s == "REMUNERADA").sum()),
            pibic_bolsas_voluntarias=("tipo_bolsa_norm", lambda s: (s == "VOLUNTARIA").sum()),
            pibic_cotistas=("is_cotista", "sum"),
            pibic_investimento_total=("valor_bolsa_anual_estimado", "sum"),
        ).reset_index()
        
        df_gold = pd.merge(
            df_gold,
            pibic_course_agg,
            left_on="curso",
            right_on="curso_pibic_norm",
            how="left",
        )
        df_gold["pibic_total_projetos"] = df_gold["pibic_total_projetos"].fillna(0).astype(int)
        df_gold["pibic_investimento_total"] = df_gold["pibic_investimento_total"].fillna(0.0)
        df_gold["pibic_projetos_por_100_alunos"] = (
            df_gold["pibic_total_projetos"] / df_gold["total_discentes_registrados"] * 100
        ).round(2)
        if "curso_pibic_norm" in df_gold.columns:
            df_gold.drop(columns=["curso_pibic_norm"], inplace=True)

    # Ordenar por índice de retenção decrescente
    df_gold = df_gold.sort_values(by="indice_retencao_critica", ascending=False)
    
    # Salvar tabela Gold
    gold_csv_path = GOLD_DIR / "retencao_cursos_unb.csv"
    df_gold.to_csv(gold_csv_path, index=False, encoding="utf-8")
    logger.info(f"Tabela analítica Gold salva em {gold_csv_path.name} com {len(df_gold)} cursos.")

    # 8.1 Benchmark Nacional por Curso (Censo da Educação Superior / INEP)
    build_inep_benchmark_gold()

    # 9. Cálculo das Métricas Globais da UnB (Resumo das 5 GQs)
    total_formados_unb = int(df_valid["is_formado"].sum())
    formados_ideal_unb = int(df_valid["formou_tempo_ideal"].sum())
    formados_acima_unb = int(df_valid["formou_acima_ideal"].sum())
    
    global_metrics = {
        "total_discentes_analisados": len(df_valid),
        "total_formados_unb": total_formados_unb,
        "taxa_conclusao_tempo_ideal_global_pct": round(formados_ideal_unb / total_formados_unb * 100, 2),
        "taxa_conclusao_acima_ideal_global_pct": round(formados_acima_unb / total_formados_unb * 100, 2),
        "tempo_medio_formatura_global_semestres": round(df_valid[df_valid["is_formado"]]["semestres_permanencia_valida"].mean(), 2),
        "desvio_medio_global_semestres": round(df_valid[df_valid["is_formado"]]["desvio_semestres_individual"].mean(), 2),
        "top_5_cursos_maior_retencao": df_gold.head(5)[["curso", "tempo_medio_real_semestres", "taxa_evasao_pct", "indice_retencao_critica"]].to_dict(orient="records"),
        "top_5_cursos_maior_pontualidade": df_gold.sort_values("formados_tempo_ideal_pct", ascending=False).head(5)[["curso", "formados_tempo_ideal_pct", "tempo_medio_real_semestres"]].to_dict(orient="records"),
    }
    
    with open(GOLD_DIR / "metricas_gerais_unb.json", "w", encoding="utf-8") as f:
        json.dump(global_metrics, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Métricas globais da UnB consolidadas em metricas_gerais_unb.json")
    return df_gold, global_metrics


def build_inep_benchmark_gold() -> pd.DataFrame:
    """
    Compara cada curso da UnB com o mesmo curso nas demais universidades federais, a partir do
    Censo da Educação Superior (INEP).

    A comparação é feita inteiramente dentro da base do INEP - os dois lados usam a mesma
    nomenclatura oficial de curso -, portanto não depende da harmonização de nomes entre SIGRA
    e matrizes curriculares usada no restante da camada Gold.

    As taxas aqui são do Censo (situação da matrícula apurada no ano-censo) e medem coisa
    diferente da taxa de evasão da tabela de retenção, que acompanha a coorte de ingresso ao
    longo do tempo no SIGRA. Ver docs/fonte_inep_censo_superior.md.
    """
    inep_path = SILVER_DIR / "inep_censo_superior_silver.csv"
    if not inep_path.exists():
        logger.warning(f"Arquivo {inep_path.name} não encontrado. Pulando benchmark INEP.")
        return pd.DataFrame()

    df = pd.read_csv(inep_path)

    # Cursos muito pequenos produzem taxas instáveis (1 aluno move vários pontos percentuais).
    df = df[df["QT_MAT"] >= MIN_MATRICULAS_BENCHMARK].copy()

    unb = df[df["is_unb"]]
    pares = df[~df["is_unb"]]

    # Lado UnB: soma as várias ofertas do mesmo curso (turnos e campi entram como registros
    # distintos no Censo) antes de calcular a taxa, para não dar peso igual a ofertas de
    # tamanhos muito diferentes.
    agg_unb = unb.groupby("NO_CURSO").agg(
        qt_matriculas_unb=("QT_MAT", "sum"),
        qt_ingressantes_unb=("QT_ING", "sum"),
        qt_concluintes_unb=("QT_CONC", "sum"),
        qt_trancadas_unb=("QT_SIT_TRANCADA", "sum"),
        qt_desvinculados_unb=("QT_SIT_DESVINCULADO", "sum"),
        qt_vagas_unb=("QT_VG_TOTAL", "sum"),
        qt_inscritos_unb=("QT_INSCRITO_TOTAL", "sum"),
    ).reset_index()
    agg_unb["taxa_trancamento_unb_pct"] = (
        agg_unb["qt_trancadas_unb"] / agg_unb["qt_matriculas_unb"] * 100
    ).round(2)
    agg_unb["taxa_desvinculacao_unb_pct"] = (
        agg_unb["qt_desvinculados_unb"] / agg_unb["qt_matriculas_unb"] * 100
    ).round(2)
    agg_unb["concorrencia_vestibular_unb"] = (
        agg_unb["qt_inscritos_unb"] / agg_unb["qt_vagas_unb"].replace(0, np.nan)
    ).round(2)

    # Lado nacional: mediana entre as demais federais (mediana, não média, para não deixar uma
    # instituição atípica distorcer o padrão de referência do curso).
    agg_pares = pares.groupby("NO_CURSO").agg(
        n_ies_comparadas=("CO_IES", "nunique"),
        mediana_trancamento_federais_pct=("taxa_trancamento_pct", "median"),
        mediana_desvinculacao_federais_pct=("taxa_desvinculacao_pct", "median"),
    ).reset_index().round(2)

    df_bench = agg_unb.merge(agg_pares, on="NO_CURSO", how="left")
    df_bench["gap_trancamento_pp"] = (
        df_bench["taxa_trancamento_unb_pct"] - df_bench["mediana_trancamento_federais_pct"]
    ).round(2)
    df_bench["gap_desvinculacao_pp"] = (
        df_bench["taxa_desvinculacao_unb_pct"] - df_bench["mediana_desvinculacao_federais_pct"]
    ).round(2)

    # A diferença em pontos percentuais achata a gravidade relativa: +6 pp sobre um curso que
    # já perde 24% em todo o país é bem menos grave que +7 pp sobre um que perde 8%. A razão
    # expõe isso (1,9x = a UnB quase dobra o padrão nacional daquele curso).
    df_bench["razao_trancamento"] = (
        df_bench["taxa_trancamento_unb_pct"] / df_bench["mediana_trancamento_federais_pct"]
    ).round(2)
    df_bench["razao_desvinculacao"] = (
        df_bench["taxa_desvinculacao_unb_pct"] / df_bench["mediana_desvinculacao_federais_pct"]
    ).round(2)
    df_bench = df_bench.rename(columns={"NO_CURSO": "curso_inep"}).sort_values(
        "qt_matriculas_unb", ascending=False
    )

    out_path = GOLD_DIR / "inep_benchmark_cursos_unb.csv"
    df_bench.to_csv(out_path, index=False, encoding="utf-8")
    comparaveis = int((df_bench["n_ies_comparadas"] >= MIN_IES_BENCHMARK).sum())
    logger.info(
        f"Benchmark INEP salvo em {out_path.name}: {len(df_bench)} cursos da UnB, "
        f"{comparaveis} com pelo menos {MIN_IES_BENCHMARK} federais comparáveis."
    )
    return df_bench


def build_pibic_gold() -> Tuple[pd.DataFrame, Dict]:
    """
    Constrói a tabela analítica Gold do PIBIC (Iniciação Científica)
    e consolida os indicadores de custo total e inclusão social.
    """
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    pibic_silver_path = SILVER_DIR / "pibic_bolsistas_silver.csv"
    
    if not pibic_silver_path.exists():
        logger.warning(f"Arquivo {pibic_silver_path.name} não encontrado. Pulando Gold do PIBIC.")
        return pd.DataFrame(), {}
        
    df_pibic = pd.read_csv(pibic_silver_path)
    total_registros = len(df_pibic)

    # Campus: mesma normalização usada na tabela de retenção, para os nomes baterem
    # entre as duas fontes (a base de bolsistas grava "FGA - GAMA"/"FCE - CEILANDIA").
    df_pibic["campus"] = df_pibic["campus"].apply(normalize_campus_nome)

    # 0. Canonicalização do curso e Grande Área oficial (CNPq/MEC)
    # O campo "unidade" da base de bolsistas gera grafias inconsistentes para o mesmo curso
    # (ex.: variações de "Letras - Tradução"), por isso passa pela mesma harmonização canônica
    # usada para o SIGRA. A "Grande Área" exibida não usa o campo "linha_pesquisa" (autodeclarado
    # pela própria base de IC, que classifica cursos como Farmácia em "ARTES E HUMANIDADE"),
    # e sim `area_conhecimento_norm` do catálogo oficial de cursos.
    df_pibic["curso_canonico"] = df_pibic["curso_pibic_norm"].replace(COURSE_ALIASES)

    cur_path = SILVER_DIR / "cursos_graduacao_silver.csv"
    if cur_path.exists():
        df_cur_cat = pd.read_csv(cur_path)
        area_dict = build_area_por_curso(df_cur_cat, df_pibic["curso_canonico"].unique())
        df_pibic["area_conhecimento"] = df_pibic["curso_canonico"].map(area_dict).fillna("OUTRA")
    else:
        df_pibic["area_conhecimento"] = df_pibic["linha_pesquisa_norm"]

    # 1. Indicadores Financeiros e Totais
    total_remuneradas = int((df_pibic["tipo_bolsa_norm"] == "REMUNERADA").sum())
    total_voluntarias = int((df_pibic["tipo_bolsa_norm"] == "VOLUNTARIA").sum())
    total_investido = float(df_pibic["valor_bolsa_anual_estimado"].sum())
    
    # 2. Indicadores Sociais (Cotas e Inclusão)
    total_cotistas = int(df_pibic["is_cotista"].sum())
    taxa_inclusao_cotistas = round((total_cotistas / total_registros * 100), 2) if total_registros else 0.0
    taxa_trabalho_voluntario = round((total_voluntarias / total_registros * 100), 2) if total_registros else 0.0
    
    # Distribuição por Perfil Social Macro
    dist_social = (
        df_pibic["perfil_social_macro"].value_counts(normalize=True) * 100
    ).round(2).to_dict()
    
    # Distribuição por Cota Detalhe
    dist_cota_detalhe = df_pibic["cota_detalhe"].value_counts().to_dict()
    
    # Distribuição por Campi
    campi_agg = df_pibic.groupby("campus").agg(
        total_projetos=("ano", "count"),
        total_remuneradas=("tipo_bolsa_norm", lambda s: (s == "REMUNERADA").sum()),
        total_cotistas=("is_cotista", "sum"),
        valor_investido=("valor_bolsa_anual_estimado", "sum"),
    ).reset_index()
    campi_agg["pct_projetos"] = (campi_agg["total_projetos"] / total_registros * 100).round(2)
    campi_agg["pct_cotistas"] = (campi_agg["total_cotistas"] / campi_agg["total_projetos"] * 100).round(2)
    dist_campi = campi_agg.to_dict(orient="records")
    
    # Distribuição por Grande Área
    area_agg = df_pibic.groupby("area_conhecimento").agg(
        total_projetos=("ano", "count"),
        total_remuneradas=("tipo_bolsa_norm", lambda s: (s == "REMUNERADA").sum()),
        total_cotistas=("is_cotista", "sum"),
        valor_investido=("valor_bolsa_anual_estimado", "sum"),
    ).reset_index()
    area_agg["pct_projetos"] = (area_agg["total_projetos"] / total_registros * 100).round(2)
    area_agg["pct_cotistas"] = (area_agg["total_cotistas"] / area_agg["total_projetos"] * 100).round(2)

    # Taxa de participação: projetos PIBIC / total de alunos matriculados na área (não só
    # % de composição do programa). Requer a tabela de retenção (roda antes no __main__).
    retencao_path = GOLD_DIR / "retencao_cursos_unb.csv"
    if retencao_path.exists():
        df_retencao = pd.read_csv(retencao_path)
        alunos_por_area = df_retencao.groupby("area_conhecimento")["total_discentes_registrados"].sum()
        area_agg["total_discentes_area"] = area_agg["area_conhecimento"].map(alunos_por_area).fillna(0).astype(int)
        area_agg["taxa_participacao_pibic_pct"] = (
            area_agg["total_projetos"] / area_agg["total_discentes_area"].replace(0, np.nan) * 100
        ).round(2)
        # "OUTRA" (curso não classificado) não tem alunos associados na área; NaN quebraria o
        # JSON estrito, então vira null explícito em vez do valor incorreto de 0%.
        area_agg["taxa_participacao_pibic_pct"] = area_agg["taxa_participacao_pibic_pct"].astype(object).where(
            area_agg["taxa_participacao_pibic_pct"].notna(), None
        )
    dist_area = area_agg.to_dict(orient="records")
    
    # Evolução Anual
    ano_agg = df_pibic.groupby("ano").agg(
        total_projetos=("tipo_bolsa_norm", "count"),
        remuneradas=("tipo_bolsa_norm", lambda s: (s == "REMUNERADA").sum()),
        voluntarias=("tipo_bolsa_norm", lambda s: (s == "VOLUNTARIA").sum()),
        cotistas=("is_cotista", "sum"),
        investimento_reais=("valor_bolsa_anual_estimado", "sum"),
    ).reset_index()
    dist_ano = ano_agg.to_dict(orient="records")
    
    # 3. Tabela Analítica Agregada por Curso / Unidade (com k-anônimo >= 5)
    # Agrupa pelo curso canônico (não o nome bruto extraído do campo "unidade"), para não
    # espalhar o mesmo curso em várias linhas por causa de grafias inconsistentes na origem.
    curso_agg = df_pibic.groupby(["curso_canonico", "campus", "area_conhecimento"]).agg(
        total_projetos=("ano", "count"),
        total_remuneradas=("tipo_bolsa_norm", lambda s: (s == "REMUNERADA").sum()),
        total_voluntarias_pivic=("tipo_bolsa_norm", lambda s: (s == "VOLUNTARIA").sum()),
        total_cotistas=("is_cotista", "sum"),
        total_cotistas_ppi=("perfil_social_macro", lambda s: (s == "PPI / ETNICO-RACIAL").sum()),
        total_baixa_renda=("faixa_renda", lambda s: (s == "BAIXA RENDA (<= 1.5 SM)").sum()),
        valor_total_investido=("valor_bolsa_anual_estimado", "sum"),
    ).reset_index().rename(columns={"curso_canonico": "curso_pibic_norm"})

    # Exclui registros sem nome de curso e aplica supressão ética k < 5
    curso_agg = curso_agg[(curso_agg["curso_pibic_norm"] != "") & (curso_agg["total_projetos"] >= 5)].copy()
    curso_agg["taxa_cotistas_pct"] = (curso_agg["total_cotistas"] / curso_agg["total_projetos"] * 100).round(1)
    curso_agg["taxa_voluntario_pct"] = (curso_agg["total_voluntarias_pivic"] / curso_agg["total_projetos"] * 100).round(1)
    curso_agg = curso_agg.sort_values(by="total_projetos", ascending=False)
    
    # Salvar tabela Gold do PIBIC
    pibic_gold_csv = GOLD_DIR / "pibic_social_unb.csv"
    curso_agg.to_csv(pibic_gold_csv, index=False, encoding="utf-8")
    
    # 4. Consolidar JSON de Métricas
    pibic_metrics = {
        "total_projetos_ic": total_registros,
        "total_bolsas_remuneradas": total_remuneradas,
        "total_pesquisadores_voluntarios_pivic": total_voluntarias,
        "investimento_publico_total_estimado": total_investido,
        "total_cotistas": total_cotistas,
        "taxa_inclusao_cotistas_pct": taxa_inclusao_cotistas,
        "taxa_trabalho_voluntario_pct": taxa_trabalho_voluntario,
        "distribuicao_perfil_social_pct": dist_social,
        "distribuicao_cota_detalhe": dist_cota_detalhe,
        "distribuicao_campi": dist_campi,
        "distribuicao_grande_area": dist_area,
        "evolucao_anual": dist_ano,
    }
    
    with open(GOLD_DIR / "pibic_metricas_gerais.json", "w", encoding="utf-8") as f:
        json.dump(pibic_metrics, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Tabela Gold PIBIC salva em {pibic_gold_csv.name} com {len(curso_agg)} cursos agregados.")
    logger.info(f"Métricas gerais do PIBIC salvas em pibic_metricas_gerais.json (Investimento: R$ {total_investido:,.2f})")
    return curso_agg, pibic_metrics


if __name__ == "__main__":
    build_gold_layer()
    build_pibic_gold()

