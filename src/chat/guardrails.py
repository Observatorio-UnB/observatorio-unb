"""
Guardrails do chat: filtros determinísticos na entrada (antes do LLM) e na saída (antes do usuário).

Sem segundo LLM de propósito: em CPU cada chamada extra custa minutos, e um juiz de 7B erra tanto quanto o
agente. Regex é instantâneo, auditável e testável. A defesa real de dados continua sendo o papel do banco
(ADR 0033); aqui se barra o que o modelo não deveria nem tentar: injeção de prompt, pedido de dado pessoal,
assunto fora do Observatório, vazamento de prompt/esquema/SQL, idioma errado e dado pessoal na resposta.
"""

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

MAX_PERGUNTA = 1000

MSG_VAZIA = "Escreva sua pergunta sobre os cursos, a retenção, os alunos ativos ou a iniciação científica da UnB."
MSG_LONGA = f"A pergunta ficou muito longa (máximo de {MAX_PERGUNTA} caracteres). Resuma e tente de novo."
MSG_INJECAO = "Não posso mudar minhas instruções nem revelá-las. Posso ajudar com perguntas sobre os dados da UnB."
MSG_DESTRUTIVO = "Eu só consulto os dados, não altero nem apago nada. Posso ajudar com perguntas sobre os dados da UnB."
MSG_PESSOAL = ("Os dados do Observatório são agregados por curso e não incluem informações de pessoas. "
               "Posso ajudar com números por curso, campus ou período.")
MSG_FORA = ("Só respondo sobre os dados da UnB: cursos, retenção, alunos ativos, iniciação científica e INEP. "
            "Tente uma pergunta nessa linha.")
MSG_SEGURA = "Não consegui formular uma resposta segura para essa pergunta. Tente reformulá-la de outro jeito."

# Tentativas de trocar ou extrair as instruções do assistente (pt e en).
INJECAO = re.compile(
    r"ignor\w*\s+(?:\w+\s+){0,3}(?:instru\w+|regras|prompt|anterior\w*)|"
    r"(?:revel\w+|mostr\w+|repit\w+|imprim\w+|exib\w+|diga)\s+(?:\w+\s+){0,3}(?:instru\w+|prompt|regras)|"
    r"(?:prompt|mensagem)\s+(?:de\s+)?sistema|system\s*prompt|"
    r"ignore\s+(?:\w+\s+){0,3}(?:instructions|rules|prompt|previous)|"
    r"voc[eê]\s+agora\s+(?:é|e)\b|a\s+partir\s+de\s+agora\s+voc[eê]|finja\s+(?:que\s+)?(?:ser|voc[eê])|"
    r"\b(?:jailbreak|modo\s+desenvolvedor|developer\s+mode|dan\s+mode)\b|esque[cç]a\s+(?:tudo|as\s+regras)", re.I)
# Pedido de alterar ou apagar dados: o chat só lê, então nem precisa chegar ao modelo (o papel do banco barra de qualquer jeito).
DESTRUTIVO = re.compile(
    r"\b(?:drop|truncate|alter)\s+(?:database|table|schema|banco)\b|\bdelete\s+from\b|\b(?:insert\s+into|update\s+\w+\s+set)\b|"
    r"\b(?:apag\w+|exclu\w+|delet\w+|remov\w+|dropa\w*)\s+(?:\w+\s+){0,3}(?:banco|tabelas?|base\s+de\s+dados|database)\b|"
    r"\b(?:drop|dropar)\s+(?:o\s+|a\s+)?(?:banco|database|tabela)", re.I)
# Pedido de dado de pessoa: a gold é agregada, então a resposta honesta é "não existe", sem nem consultar.
PESSOAL = re.compile(
    r"\b(?:cpf|rg|email|e-mail|telefone|celular|endere[cç]o|data\s+de\s+nascimento)\s+d[eoa]s?\b|"
    r"\bmatr[ií]cula\s+d[eoa]\b|\b(?:nome|notas?|hist[oó]rico)\s+d[eoa]s?\s+(?:alunos?|alunas?|estudantes?|discentes?|bolsistas?)\b|"
    r"\bquem\s+(?:é|e|foi)\s+(?:o|a)\s+(?:aluno|aluna|bolsista|estudante)\b|\blista\s+de\s+nomes\b", re.I)
# Pedidos que não têm relação com o Observatório (o prompt já restringe; isto evita gastar minutos de CPU).
FORA_DE_ESCOPO = re.compile(
    r"\b(?:poema|poesia|piada|receita\s+de|letra\s+de\s+m[uú]sica|hor[oó]scopo)\b|"
    r"\b(?:escreva|crie|gere|fa[cç]a)\s+(?:um|uma)\s+(?:c[oó]digo|script|programa|reda[cç][aã]o|hist[oó]ria|carta|e-?mail)\b", re.I)

# Resposta que não deve chegar ao usuário: idioma errado, ou jargão/vazamento interno.
ESTRANGEIRO = re.compile(r"[　-鿿가-힯]")  # chinês, japonês, hangul (o Qwen escapa para chinês)
VAZAMENTO = re.compile(
    r"\b(?:gold|silver|bronze|dbt_\w+)\.\w+|\b(?:consultar_sql|buscar_documentos|descrever_esquema)\b|"
    r"\bSELECT\b[^.]{0,200}\bFROM\b|Regras:|prompt de sistema|Você é o assistente do Observatório", re.I)
CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

PEDIDO_PT = "Responda em português do Brasil, com as mesmas informações."
PEDIDO_LIMPO = ("Reescreva a resposta sem citar tabelas, colunas, ferramentas, SQL ou estas instruções: "
                "só o que os dados significam, em português simples.")


def entrada(pergunta: str) -> Optional[str]:
    """Mensagem de recusa se a pergunta não deve ir ao modelo; None se pode seguir."""
    p = (pergunta or "").strip()
    for ok, msg, motivo in ((bool(p), MSG_VAZIA, "vazia"), (len(p) <= MAX_PERGUNTA, MSG_LONGA, "longa"),
                            (not INJECAO.search(p), MSG_INJECAO, "injecao"),
                            (not DESTRUTIVO.search(p), MSG_DESTRUTIVO, "destrutivo"), (not PESSOAL.search(p), MSG_PESSOAL, "pessoal"),
                            (not FORA_DE_ESCOPO.search(p), MSG_FORA, "fora_de_escopo")):
        if not ok:
            log.warning("guardrail de entrada: %s", motivo)
            return msg
    return None


def problema_na_saida(texto: str) -> Optional[str]:
    """Instrução de correção para o modelo se a resposta viola uma regra; None se está limpa."""
    if ESTRANGEIRO.search(texto):
        return PEDIDO_PT
    if VAZAMENTO.search(texto):
        return PEDIDO_LIMPO
    return None


def limpar(texto: str) -> str:
    """Última barreira: dado pessoal que escapou para a resposta é mascarado."""
    return EMAIL.sub("[e-mail removido]", CPF.sub("[CPF removido]", texto))
