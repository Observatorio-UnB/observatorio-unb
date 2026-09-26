# ADR 0010: Papel de leitura que só enxerga gold e busca

- **Status:** Aceita
- **Data:** 2026-09-24

## Contexto

Bronze e Silver no banco têm registro individual de discente.

## Decisão

Papel `observatorio_leitura` com `SELECT` apenas nos esquemas `gold` e `busca` (e privilégio padrão para tabelas futuras). Usuários de consulta herdam esse papel.

## Consequências

Consultas analíticas não têm como ler dado pessoal por engano. Quem precisa da Silver usa o usuário dono do banco.
