# Fonte: Censo da Educação Superior (INEP/MEC)

## O que é e por que entrou no projeto

O Censo da Educação Superior é o levantamento anual do INEP sobre todas as graduações do país
(253.139 cursos na edição de 2019). Ele entrou no projeto para responder uma pergunta que as
bases da própria UnB não conseguem responder: **a UnB perde mais alunos do que as outras
universidades federais no mesmo curso?**

Traz também o **trancamento de matrícula**, informação que não existe em nenhuma outra fonte do
projeto — o SIGRA registra apenas saídas definitivas, não a suspensão temporária do vínculo.

## Situação legal e privacidade

Dado público, publicado pelo INEP em *Acesso à Informação > Dados Abertos*, sem cadastro,
autenticação ou aceite de termos. O manual do usuário que acompanha o pacote declara:

> "em atendimento à Lei nº 12.527, de 18 de novembro de 2011 (Lei de Acesso à Informação), e
> Lei nº 13.709, de 14 de agosto de 2018 (Lei Geral de Proteção de Dados Pessoais), a partir de
> agora os Microdados do Censo da Educação Superior passam a ser estruturados ao nível de
> Instituições de Ensino Superior (IES) e cursos"

Apesar do nome "microdados", **não há registro individual de discente**: os arquivos publicados
são `MICRODADOS_CADASTRO_CURSOS` (uma linha por curso) e `MICRODADOS_CADASTRO_IES` (uma linha por
instituição), e todas as ~200 colunas de conteúdo são contagens (`QT_*`). Não há nome, CPF, data
de nascimento nem qualquer quase-identificador — ao contrário do `sigra_discentes.csv`, que exigiu
a análise de reidentificação em [registro_privacidade_lgpd.md](registro_privacidade_lgpd.md).

## Origem e recorte

- **Arquivo**: `https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2019.zip`
- **Ingestão**: `src/ingestion/inep_censo_superior.py`
- **Recorte gravado na Bronze**: cursos **presenciais** de **universidades públicas federais**
  (4.826 cursos, 63 instituições). O arquivo bruto do INEP tem 143 MB; o recorte comparável com a
  UnB tem menos de 1 MB.
- **UnB no cadastro do INEP**: `CO_IES = 2`.

## Por que o ano-base é 2019, e não o mais recente

O Censo 2023 existe e é acessível, mas o número de trancamentos reportado pela UnB nele é
inconsistente com o resto do sistema:

| Ano | Trancamento UnB | Trancamento médio das federais |
|---|---|---|
| 2019 | 8,4% | 8,7% |
| 2020 | 11,4% | 22,2% |
| 2023 | **1,0%** | **14,6%** |

Em 2023 a taxa nacional sobe e a da UnB cai oito vezes, na contramão — padrão típico de mudança
de critério no preenchimento do Censo, não de fenômeno real. Além disso, 2019 fica **dentro da
janela temporal do SIGRA** (2010-2020) usada no restante do painel, o que mantém a coerência
do dashboard.

## Cuidado de interpretação (importante)

As taxas do Censo **não são a mesma coisa** que a taxa de evasão da tabela de retenção:

| | Taxa de evasão (tabela de retenção) | Taxas do Censo (INEP) |
|---|---|---|
| Base | Histórico do SIGRA | Censo da Educação Superior |
| Método | Acompanha a coorte de ingresso até a saída | Fotografa a situação das matrículas no ano-censo |
| Responde | "Dos que entraram, quantos saíram sem concluir?" | "Das matrículas ativas neste ano, quantas foram trancadas/desvinculadas?" |

Os dois números são corretos, medem coisas diferentes e não devem ser somados nem comparados
diretamente. O dashboard sinaliza isso na própria aba.

## Detalhe técnico: cadeia TLS incompleta

O servidor `download.inep.gov.br` não envia o certificado intermediário da sua autoridade
certificadora (RNP/ICPEdu). Navegadores buscam esse intermediário sozinhos; `curl`, `requests` e
`urllib` não, e falham com "unable to get local issuer certificate". O script de ingestão trata
isso baixando o intermediário da URL declarada no próprio certificado do servidor (extensão
*Authority Information Access*) e anexando-o ao bundle de CAs antes de repetir a requisição. O
servidor também derruba conexões de forma intermitente, por isso o download tem novas tentativas
espaçadas.

## Limitações

1. **Comparação por nome de curso**: assume que cursos de mesmo nome em federais diferentes são
   equivalentes. "Engenharia Química" na UnB e na UFMG têm currículos distintos, ainda que o
   nome e a área sejam os mesmos.
2. **Corte mínimo**: a comparação só considera cursos com pelo menos 50 matrículas e pelo menos
   10 federais oferecendo o mesmo curso (`MIN_MATRICULAS_BENCHMARK` e `MIN_IES_BENCHMARK` em
   `src/pipeline/build_gold.py`). Em cursos menores, um único aluno desloca a taxa vários pontos
   percentuais, e meia dúzia de instituições não caracteriza um padrão nacional.
3. **Um único ano**: é uma fotografia de 2019, não uma série temporal.
4. **Qualidade depende do preenchimento de cada IES**: o próprio caso do trancamento da UnB em
   2023, descrito acima, mostra que o dado reflete o que cada instituição declarou ao Censo.
