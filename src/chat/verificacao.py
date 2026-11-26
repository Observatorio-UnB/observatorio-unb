"""
Checagem de ancoragem: todo número da resposta do modelo precisa vir de um resultado de ferramenta, da
pergunta ou do prompt de sistema. Não impede a resposta, mas devolve os números sem fonte para a interface
avisar (modelo de 7B inventa ou arredonda número, e o usuário deve conferir).
"""

import re
from typing import Iterable, List


def numeros(texto: str) -> List[float]:
    """Números do texto, aceitando 1.234,56 (pt-BR) e 1,234.56. Um grupo de três dígitos depois de
    separador ("38,409", "12.527") é ambíguo entre decimal e milhar: vale as duas leituras."""
    achados = []
    for m in re.findall(r"\d[\d.,]*", texto):
        m = m.rstrip(".,")
        if "," in m and "." in m:
            leituras = [m.replace(".", "").replace(",", ".") if m.rfind(",") > m.rfind(".") else m.replace(",", "")]
        else:
            leituras = [m.replace(",", ".")]  # vírgula decimal
            if re.fullmatch(r"\d{1,3}([.,]\d{3})+", m):
                leituras.append(re.sub(r"[.,]", "", m))  # ou separador de milhar
        for x in leituras:
            try:
                achados.append(float(x))
            except ValueError:
                pass
    return achados


def perto(a: float, b: float) -> bool:
    # A tolerância absoluta (arredondamento de decimais) só vale se a fonte tem casas decimais:
    # contagem inteira tem de bater ("9 alunos" contra 5, ou 0,04 contra 0, são erros).
    return abs(a - b) <= max(0.06 if b != int(b) else 0, 0.005 * abs(b))


def numeros_sem_fonte(resposta: str, fontes: Iterable[str]) -> List[str]:
    """Números da resposta sem equivalente nas fontes (a pergunta é fonte: "os 5 cursos" passa).
    Marcadores de lista numerada ("1.") não contam."""
    resposta = re.sub(r"(?m)^\s*\d+[.)]\s", "", resposta)
    conhecidos = [n for f in fontes for n in numeros(f)]
    sem = []
    for tok in re.findall(r"\d[\d.,]*", resposta):
        tok = tok.rstrip(".,")
        leituras = numeros(tok)
        if not any(perto(n, c) for n in leituras for c in conhecidos):
            sem.append(tok)
    return sem
