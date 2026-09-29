"""
Módulo de Análise de Privacidade e Conformidade LGPD (Dia 5 - Semana 1)
Avalia analiticamente a presença de quase-identificadores na base do SIGRA e do SIGAA,
mede o nível de k-anonimato e unicidade e documenta as salvaguardas éticas.
"""

import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lgpd_check")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = BASE_DIR / "docs"
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.tabelas import tem_linhas  # noqa: E402

TABELAS_DISCENTES = {
    "SIGRA": "bronze.sigra_discentes",
    "SIGAA": "bronze.sigaa_discentes",
}


def _grupos_de_equivalencia(tabela: str) -> Tuple[int, Counter]:
    """Conta os grupos de (curso, data_nascimento, sexo, raca_cor) entre os vínculos de graduação."""
    if not tem_linhas(tabela):
        return 0, Counter()
    with conectar() as conn:
        linhas = conn.execute(
            f"SELECT nivel, curso, data_nascimento, sexo, raca_cor FROM {tabela}"
        ).fetchall()
    total = 0
    grupos = Counter()
    for nivel, curso, dt_nasc, sexo, raca in linhas:
        if (nivel or "").strip().upper().startswith("GRADUA"):
            total += 1
            c = (curso or "").strip().upper()
            dt = (dt_nasc or "").strip()
            s = (sexo or "").strip().upper()
            r = (raca or "").strip().upper()
            grupos[(c, dt, s, r)] += 1
    return total, grupos


def analyze_quasi_identifiers() -> Tuple[Dict, str]:
    """Calcula estatísticas de unicidade e k-anonimato sobre as bases de discentes (SIGRA e SIGAA).

    Cada base é avaliada em separado: são publicadas como arquivos distintos e os pseudônimos
    não se ligam entre si, então o risco de reidentificação é o de cada arquivo.
    """
    stats = {}
    for base, tabela in TABELAS_DISCENTES.items():
        total, grupos = _grupos_de_equivalencia(tabela)
        unicos = sum(1 for n in grupos.values() if n == 1)
        stats[base] = {
            "tabela": tabela,
            "total_discentes_graduacao": total,
            "total_combinacoes": len(grupos),
            "registros_unicos_k1": unicos,
            "percentual_unicidade": (unicos / total * 100) if total else 0,
            "k_minimo": min(grupos.values()) if grupos else 0,
            "distribuicao_k": dict(Counter(grupos.values()).most_common(5)),
        }

    md = []
    md.append(
        "# Registro de Risco de Privacidade e Avaliação LGPD (Dia 5 - Semana 1)")
    md.append("\n**Projeto**: Análise de Retenção e Formatura nos Cursos da UnB")
    md.append("**Bases Analisadas**: " + ", ".join(
        f"`{b['tabela']}`" for b in stats.values()) + " (Graduação)")
    md.append("\n---\n")

    md.append("## 1. Avaliação Analítica de Quase-Identificadores e k-Anonimato\n")
    md.append(
        "- **Quase-identificadores Testados**: `(curso, data_nascimento, sexo, raca_cor)`")
    md.append("- Cada base é avaliada em separado: são arquivos distintos no portal, com pseudônimos que não se ligam.\n")
    md.append(
        "- **Risco de reidentificação**: registro com k = 1 é o único aluno com aquela combinação de "
        "curso, nascimento, sexo e raça/cor; quem conhece esses dados de um colega o encontra na base "
        "e descobre forma de ingresso, cota e forma de saída. Por isso a base individual não é publicada.\n")
    md.append(
        "| Base | Registros de Graduação | Registros com k = 1 (Unicidade Absoluta) | k Mínimo |")
    md.append("| :--- | :--- | :--- | :--- |")
    for base, b in stats.items():
        md.append(
            f"| {base} | {b['total_discentes_graduacao']:,} | {b['registros_unicos_k1']:,} "
            f"({b['percentual_unicidade']:.2f}%) | k = {b['k_minimo']} |"
        )

    for base, b in stats.items():
        md.append(
            f"\n### Distribuição de Frequência de Grupos de Equivalência ({base}):")
        md.append("| Tamanho do Grupo (k) | Quantidade de Grupos | Descrição |")
        md.append("| :--- | :--- | :--- |")
        for k_val, count in b["distribuicao_k"].items():
            desc = "Identificação unívoca (risco máximo)" if k_val == 1 else f"Grupo com {k_val} pessoas indistinguíveis"
            md.append(f"| k = {k_val} | {count:,} grupos | {desc} |")

    md.append("\n---\n")
    md.append(
        "## 2. Enquadramento Legal e Princípios da LGPD (Lei nº 13.709/2018)\n")
    md.append("1. **Dado Pessoal vs. Anonimizado (Art. 5º, I e III)**:")
    md.append("   - Embora nomes e CPFs completos tenham sido retirados no SIGRA e no SIGAA, a presença conjunta de data de nascimento exata, sexo, raça e cota configura *dados pessoais indiretos* (quase-identificadores).")
    md.append("   - Pseudonimização não equivale a anonimização: a reidentificação é viável cruzando com listas de vestibular ou diários oficiais.")
    md.append("2. **Princípio da Finalidade e Necessidade (Art. 6º, I e III)**:")
    md.append("   - O portal da transparência visa a prestação de contas pública. Contudo, dados demográficos sensíveis (raça/cor, data de nascimento) não são necessários para a finalidade de auditar o tempo de curso individualmente.")
    md.append("3. **O que é ESTRITAMENTE PROIBIDO neste Projeto**:")
    md.append(
        "   - ❌ Executar qualquer rotina de cruzamento com fontes externas para reidentificar discentes;")
    md.append("   - ❌ Republicar ou expor microdados de discentes em nível individual no repositório ou no dashboard;")
    md.append("   - ❌ Realizar inferências sobre indivíduos específicos.")

    md.append("\n---\n")
    md.append("## 3. Salvaguardas Metodológicas e Regras da Camada Gold\n")
    md.append("Para mitigar 100% dos riscos e garantir conformidade ética:")
    md.append("1. **Agregação Obrigatória**: Todas as métricas de tempo real de formatura, retenção e evasão são calculadas e agregadas exclusivamente por `curso` e `departamento`.")
    md.append("2. **Supressão de Pequenos Grupos**: Qualquer agregação que envolva menos de 5 discentes terá os detalhes suprimidos para assegurar $k \\ge 5$.")
    md.append("3. **Descarte de Quase-Identificadores Sensíveis**: As colunas `data_nascimento`, `sexo` e `raca_cor` são eliminadas na transformação da camada Silver para a Gold.")
    md.append("4. **Minimização dos Arquivos Nominais**: O portal publica `SIGAA_Concluintes_*` e a lista `sigaa_ativos_AAAA_S.csv` com nome completo e CPF parcial. Os de concluintes não são baixados. Da lista de ativos, a ingestão (`src/ingestion/ckan_client.py`) lê o arquivo em memória e grava só `grau`, `curso`, `ano_ingresso` e `periodo_ingresso`: nome, CPF e nacionalidade nunca chegam ao disco, ao banco nem ao CI (LGPD, art. 6º, III). O mesmo vale para os bolsistas de IC: a ingestão grava só ano, título, tipo de bolsa, linha de pesquisa, cota, vigência, unidade e situação, sem nome e matrícula do discente nem nome do orientador.")

    return stats, "\n".join(md)


def run_privacy_check():
    """Executa a análise de privacidade e grava o documento em docs/registro_privacidade_lgpd.md."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stats, report_md = analyze_quasi_identifiers()

    out_file = DOCS_DIR / "registro_privacidade_lgpd.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_md)

    logger.info(
        f"Registro de privacidade LGPD gerado com sucesso em {out_file}")
    for base, b in stats.items():
        logger.info(
            f"{base}: {b['percentual_unicidade']:.2f}% de registros unívocos (k=1) na base bruta.")
    return stats


if __name__ == "__main__":
    run_privacy_check()
