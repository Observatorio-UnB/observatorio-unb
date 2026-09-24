"""
Módulo de Análise de Privacidade e Conformidade LGPD (Dia 5 - Semana 1)
Avalia analiticamente a presença de quase-identificadores na base do SIGRA,
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


def analyze_quasi_identifiers() -> Tuple[Dict, str]:
    """Calcula estatísticas de unicidade e k-anonimato sobre os dados de discentes."""
    # Direto do cursor: nulo chega como None, como o campo vazio chegava do csv.DictReader.
    with conectar() as conn:
        linhas = conn.execute(
            "SELECT nivel, curso, data_nascimento, sexo, raca_cor FROM bronze.sigra_discentes"
        ).fetchall()
    if not linhas:
        raise RuntimeError("bronze.sigra_discentes está vazia. Rode a ingestão (src/ingestion/ckan_client.py).")

    total_records = 0
    # Quase-identificadores: (curso, data_nascimento, sexo, raca_cor)
    comb_counter = Counter()

    for nivel, curso, dt_nasc, sexo, raca in linhas:
        if (nivel or "").strip() == "Graduação":
            total_records += 1
            curso = (curso or "").strip().upper()
            dt_nasc = (dt_nasc or "").strip()
            sexo = (sexo or "").strip()
            raca = (raca or "").strip()

            key = (curso, dt_nasc, sexo, raca)
            comb_counter[key] += 1
                
    unique_count = sum(1 for count in comb_counter.values() if count == 1)
    k_min = min(comb_counter.values()) if comb_counter else 0
    k_distribution = Counter(comb_counter.values())
    
    perc_unique = (unique_count / total_records * 100) if total_records else 0
    
    stats = {
        "total_discentes_graduacao": total_records,
        "total_combinacoes": len(comb_counter),
        "registros_unicos_k1": unique_count,
        "percentual_unicidade": perc_unique,
        "k_minimo": k_min,
        "distribuicao_k": dict(k_distribution.most_common(5)),
    }
    
    md = []
    md.append("# Registro de Risco de Privacidade e Avaliação LGPD (Dia 5 - Semana 1)")
    md.append("\n**Projeto**: Análise de Retenção e Formatura nos Cursos da UnB")
    md.append("**Base Analisada**: `bronze.sigra_discentes` (Graduação)")
    md.append("\n---\n")
    
    md.append("## 1. Avaliação Analítica de Quase-Identificadores e k-Anonimato\n")
    md.append(f"- **Total de Registros de Graduação Avaliados**: {total_records:,}")
    md.append(f"- **Quase-identificadores Testados**: `(curso, data_nascimento, sexo, raca_cor)`")
    md.append(f"- **Registros com k = 1 (Unicidade Absoluta)**: {unique_count:,} ({perc_unique:.2f}% dos discentes)")
    md.append(f"- **k-Anonimato Mínimo da Base Bruta**: k = {k_min}")
    
    md.append("\n### Distribuição de Frequência de Grupos de Equivalência:")
    md.append("| Tamanho do Grupo (k) | Quantidade de Grupos | Descrição |")
    md.append("| :--- | :--- | :--- |")
    for k_val, count in k_distribution.most_common(5):
        desc = "Identificação unívoca (risco máximo)" if k_val == 1 else f"Grupo com {k_val} pessoas indistinguíveis"
        md.append(f"| k = {k_val} | {count:,} grupos | {desc} |")
        
    md.append("\n---\n")
    md.append("## 2. Enquadramento Legal e Princípios da LGPD (Lei nº 13.709/2018)\n")
    md.append("1. **Dado Pessoal vs. Anonimizado (Art. 5º, I e III)**:")
    md.append("   - Embora nomes e CPFs completos tenham sido retirados no SIGRA, a presença conjunta de data de nascimento exata, sexo, raça e cota configura *dados pessoais indiretos* (quase-identificadores).")
    md.append("   - Pseudonimização não equivale a anonimização: a reidentificação é viável cruzando com listas de vestibular ou diários oficiais.")
    md.append("2. **Princípio da Finalidade e Necessidade (Art. 6º, I e III)**:")
    md.append("   - O portal da transparência visa a prestação de contas pública. Contudo, dados demográficos sensíveis (raça/cor, data de nascimento) não são necessários para a finalidade de auditar o tempo de curso individualmente.")
    md.append("3. **O que é ESTRITAMENTE PROIBIDO neste Projeto**:")
    md.append("   - ❌ Executar qualquer rotina de cruzamento com fontes externas para reidentificar discentes;")
    md.append("   - ❌ Republicar ou expor microdados de discentes em nível individual no repositório ou no dashboard;")
    md.append("   - ❌ Realizar inferências sobre indivíduos específicos.")
    
    md.append("\n---\n")
    md.append("## 3. Salvaguardas Metodológicas e Regras da Camada Gold\n")
    md.append("Para mitigar 100% dos riscos e garantir conformidade ética:")
    md.append("1. **Agregação Obrigatória**: Todas as métricas de tempo real de formatura, retenção e evasão são calculadas e agregadas exclusivamente por `curso` e `departamento`.")
    md.append("2. **Supressão de Pequenos Grupos**: Qualquer agregação que envolva menos de 5 discentes terá os detalhes suprimidos para assegurar $k \\ge 5$.")
    md.append("3. **Descarte de Quase-Identificadores Sensíveis**: As colunas `data_nascimento`, `sexo` e `raca_cor` são eliminadas na transformação da camada Silver para a Gold.")

    return stats, "\n".join(md)


def run_privacy_check():
    """Executa a análise de privacidade e grava o documento em docs/registro_privacidade_lgpd.md."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stats, report_md = analyze_quasi_identifiers()
    
    out_file = DOCS_DIR / "registro_privacidade_lgpd.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report_md)
        
    logger.info(f"Registro de privacidade LGPD gerado com sucesso em {out_file}")
    logger.info(f"Estatísticas: {stats['percentual_unicidade']:.2f}% de registros unívocos (k=1) na base bruta.")
    return stats


if __name__ == "__main__":
    run_privacy_check()
