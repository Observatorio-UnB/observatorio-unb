# Guia de Apresentação: Entrega E2 — Ingestão em Lote e Captura de Mudanças

Este documento é o roteiro de fala da apresentação da E2 de Banco de Dados 2. A apresentação mostra os dois caminhos do dado até o lago analítico em formato aberto, as medições que sustentam a escolha do mecanismo de ingestão (ADR 0025) e as demonstrações que provam a semântica de entrega e o tratamento do dado atrasado.

A apresentação interativa fica no próprio painel: `streamlit run src/dashboard/app.py` e abrir `http://localhost:8501/?ap2`.

---

## 1. Diretrizes Gerais da Apresentação

- **Duração ideal**: 5 a 7 minutos.
- **Foco da fala**: os dois caminhos e como cada um falhou, a opção nula medida com número, a semântica de entrega demonstrada e o dado atrasado tratado explicitamente.
- **Postura**: mostrar a medição antes da conclusão. A E2 pede "demonstre, não afirme": sempre que possível, clique no botão da demonstração ao vivo.
- **Números**: todos os números dos slides estão nos ADRs 0024, 0025 e 0026 e no README. Não arredonde nem invente: se perguntarem algo que não foi medido, diga que não foi medido.

### Antes de começar

1. Gerar o lago em lote, se ainda não existir: `python3 src/db/exportar_lago.py`.
2. Subir o banco: `docker compose up -d db` e `python3 src/db/migrar.py`.
3. Para as demonstrações do CDC, subir o profile `cdc` e registrar o conector:
   ```bash
   docker compose --profile cdc up -d db kafka connect
   bash scripts/cdc.sh registrar
   python3 src/cdc/consumidor.py --ate-esvaziar
   ```
4. Abrir o painel em `?ap2` e clicar uma vez em cada demonstração, para confirmar que o lago e o banco respondem.

---

## 2. Roteiro Passo a Passo de Apresentação

### Bloco 1: Abertura e os Dois Caminhos (Slides 1 e 2, aprox. 45 segundos)

**O que mostrar na tela**:
- Slide 1 (capa) e Slide 2 (dois caminhos até o lago).

**O que falar**:
> "Na E2, o dado sai do OLTP e chega ao armazenamento analítico por dois caminhos de natureza diferente.
> O OLTP é a Silver 3NF que modelamos na E1: cursos, estruturas curriculares e vínculos.
> O primeiro caminho é em lote: a fonte pública passa pelo medalhão, chega à Silver 3NF e é exportada para um lago Delta. O segundo é o CDC: as mudanças saem do WAL do PostgreSQL por decodificação lógica, passam pelo Debezium e pelo Kafka e chegam a outro lago Delta.
> O ponto é que eles falham de jeitos diferentes, e vamos mostrar as duas falhas."

---

### Bloco 2: Lote Idempotente e Formato Aberto (Slides 3 a 5, aprox. 90 segundos)

**O que mostrar na tela**:
- Slide 3: clicar em **Ler o histórico do Delta de movimentacoes_vinculos** e depois em **Reexecutar o export dos vínculos duas vezes** (precisa do banco no ar com a Silver 3NF carregada; leva poucos segundos).
- Slide 4: clicar em **Abrir os arquivos Parquet do lago em lote**.
- Slide 5: tabela de compressão.

**O que falar**:
> "O lote é idempotente por substituição: no banco, `TRUNCATE` e `COPY` numa transação; no lago, um `overwrite` numa versão nova do Delta. O histórico mostra várias execuções, e o número de linhas é o mesmo em todas.
> E não precisa acreditar no histórico: vou reexecutar o export agora, duas vezes. A versão do Delta sobe, mas as linhas, os arquivos ativos e o sha256 do conteúdo ficam iguais. Para contraste, a mesma tabela gravada duas vezes em modo append dá o dobro de linhas: é o erro do reprocessamento que duplica.
> Escolhemos Delta, e não Iceberg, porque o delta-rs grava de Python sem JVM nem catálogo, e porque o overwrite com predicado troca só uma janela numa transação. Perdemos a evolução de esquema mais rica do Iceberg, mas aqui o esquema vem das migrações do PostgreSQL.
> O dado não fica refém do motor: aqui eu abro os arquivos com o `pyarrow.parquet`, que não sabe nada de Delta, e leio as linhas e o codec direto do rodapé.
> Particionamos por quinquênio de ingresso, o filtro mais comum. São três arquivos de 370 a 560 KB. Por ano, seriam arquivos de uns 100 KB: o problema dos arquivos pequenos.
> A compressão foi medida no padrão de acesso real, uma agregação por curso e coorte no DuckDB. O ZSTD ocupa 35% menos que o Snappy, que é o padrão do pyarrow, e a diferença de leitura fica dentro do ruído."

---

### Bloco 3: CDC e Semântica de Entrega (Slides 6 e 7, aprox. 90 segundos)

**O que mostrar na tela**:
- Slide 6: clicar em **Consultar a publicação e o slot** e em **Ler o lago CDC de silver.cursos**.
- Slide 7: clicar em **Calcular o sha256 do lago CDC** e depois em **Forçar os reprocessamentos do CDC agora** (precisa do profile `cdc` no ar e do conector registrado; levou 1min43s no teste, então comece a falar enquanto roda).

**O que falar**:
> "O CDC viu mudança de verdade: o script `demonstrar.py` insere, altera e exclui um curso no OLTP e mede quanto cada mudança leva até o lago, entre 0,44 e 0,87 segundo.
> A semântica de entrega é no mínimo uma vez no transporte e exatamente uma vez no efeito. O offset só é confirmado no Kafka depois da gravação no lago. E o `MERGE` só aplica um evento mais novo, pela posição no WAL, que a linha do lago.
> Vou forçar os reprocessamentos agora, ao vivo, e enquanto roda eu explico. São três: o consumidor cai entre gravar e confirmar, o grupo relê os tópicos do primeiro offset, e o grupo relê tudo de novo depois de excluir as linhas. Nos três casos, o sha256 do lago, incluindo a hora de gravação de cada linha, não muda. Nenhuma linha é regravada e nenhuma linha excluída ressuscita.
> Se confirmássemos o offset antes de gravar, teríamos no máximo uma vez, e uma queda perderia o lote em silêncio."

---

### Bloco 4: Dado Atrasado (Slide 8, aprox. 60 segundos)

**O que mostrar na tela**:
- Slide 8: clicar em **Consultar as cargas e as chegadas**.

**O que falar**:
> "No nosso domínio, o dado atrasado é real: uma formatura só aparece no arquivo quando o diploma é registrado. Medimos esse atraso no SIGRA: o p99 é de 105 dias.
> A marca d'água usa 4 meses de tolerância, o que cobre o p99. Cada carga grava a marca e um retrato das contagens, e uma view classifica o que chegou como no prazo, atrasado ou sem período, e marca quando a mudança revisa uma coorte já publicada.
> Escolhemos aceitar o dado atrasado, e não descartar: a fonte é a referência, e descartar deixaria a gold divergindo do portal para sempre.
> No lago, `--janelas-alteradas` regrava só os quinquênios que mudaram."

---

### Bloco 5: A Decisão e as Falhas (Slides 9 e 10, aprox. 60 segundos)

**O que mostrar na tela**:
- Slide 9 (tabela do ADR 0025) e Slide 10 (como cada caminho falhou).

**O que falar**:
> "O ADR da E2 compara o CDC com a opção nula: não ter CDC, e seguir com a recarga agendada, que já recarrega a Silver 3NF por `TRUNCATE` e `INSERT ... SELECT` e exporta o resultado para o lago. O CDC leva a mudança ao lago em menos de um segundo, mas custa 1,9 GB de RAM em Kafka e Connect, 378 MB de tópicos e um slot de replicação que segura WAL no banco.
> A fonte muda uma vez por mês. Por isso, a recarga periódica é o mecanismo principal, e o CDC é opcional, para escrita fora do pipeline.
> E o mês vem do agendamento, não do mecanismo: um cron de hora em hora custaria praticamente o mesmo.
> Os dois caminhos falharam de jeitos diferentes. O lote falha alto: a carga cai e a transação volta. O CDC falha em silêncio: o Debezium ignora `TRUNCATE` por padrão, e as linhas apagadas ficariam vivas no lago. Um DELETE seguido de um INSERT antigo reprocessado ressuscitaria a linha. Cada uma dessas falhas tem tratamento e teste."

---

### Bloco 6: Checklist e Conclusão (Slide 11, aprox. 30 segundos)

**O que mostrar na tela**:
- Slide 11 (checklist com as evidências).

**O que falar**:
> "Fechando: os oito itens do checklist têm evidência no repositório, os testes que não precisam de banco nem de Kafka rodam no CI, e a entrega está marcada pela tag `e2`."

---

## 3. Guia de Defesa: Perguntas Prováveis e Como Responder

### Pergunta 1: *"Se a recarga é o mecanismo principal, por que montar o CDC?"*
- **Resposta**:
  > "Porque a E2 pede os dois caminhos, e porque só medindo o CDC dava para dizer com número que ele não vale a pena como caminho principal. Ele fica opcional para o caso em que alguém escreve no OLTP fora do pipeline, como numa correção manual de um curso: a recarga só levaria essa correção ao lago no mês seguinte, e o CDC leva em menos de um segundo."

---

### Pergunta 2: *"Como vocês sabem que é exatamente uma vez, e não no mínimo uma vez?"*
- **Resposta**:
  > "No transporte é no mínimo uma vez: o Kafka entrega o lote de novo depois da queda, e a demonstração mostra isso. O exatamente uma vez é no efeito, e vem da idempotência do `MERGE`: ele só aplica um evento com posição no WAL maior que a da linha no lago. A prova é o sha256 do lago inteiro, incluindo a hora de gravação, que não muda depois de três reprocessamentos."

---

### Pergunta 3: *"O que acontece com um evento que chega muito atrasado?"*
- **Resposta**:
  > "Ele é aceito e registrado. A view `silver.chegadas_por_carga` classifica a mudança como `ATRASADA` quando o período já estava fechado pela marca d'água da carga anterior, e marca se ela revisa uma coorte já publicada na gold. A gold é recalculada, e o lago regrava só a janela que mudou."

---

### Pergunta 4: *"Por que Delta e não Iceberg?"*
- **Resposta**:
  > "Pelo critério de operação: o delta-rs grava de Python sem JVM e sem catálogo, e o Iceberg em Python exige um catálogo, que seria mais um serviço no compose. E o overwrite com predicado do Delta é exatamente o que o reprocessamento de janela precisa. A evolução de esquema do Iceberg é mais rica, mas o nosso esquema vem das migrações e muda pouco."

---

### Pergunta 5: *"Rodar o lote duas vezes não duplica?"*
- **Resposta**:
  > "Não. No banco, a carga é `TRUNCATE` e `COPY` numa transação. No lago, cada execução é um `overwrite` numa versão nova. No slide 3 eu reexecuto o export ao vivo, duas vezes, e o sha256 do conteúdo não muda. Há teste para isso em `tests/test_unit_lago.py`."

---

## 4. Dicas de Oratória e Navegação Durante a Apresentação

1. **Teste as demonstrações antes**: sem o lago ou sem o banco, o botão mostra o erro e o comando para corrigir, mas perder tempo na frente da turma pesa.
2. **Tenha os ADRs abertos**: `docs/adr/0024-lago-delta-parquet-zstd.md`, `docs/adr/0025-mecanismo-de-ingestao-recarga-e-cdc.md` e `docs/adr/0026-dado-atrasado-marca-dagua.md`.
3. **Assuma os limites**: as demonstrações do CDC (`demonstrar.py` e o botão de reprocessamento do slide 7) precisam de Kafka e Debezium no ar. Sem eles, o botão avisa como subir, e a tabela do slide 7 traz a última execução registrada no README.
4. **Depois de apresentar**: `bash scripts/cdc.sh remover` apaga o conector e o slot de replicação, para o slot não segurar WAL no banco.
