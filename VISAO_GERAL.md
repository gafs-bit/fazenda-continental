# Visão geral

# Como funciona 
Exportações brutas (CSV/XLSX do sistema GSB da fazenda)
        ↓  scripts de carga (um por tipo de arquivo)
Postgres — banco gbrain_dev, três tabelas:
        pesagens            (400 linhas   — registros de pesagem/romaneio)
        fretes_colheita     (22 linhas    — frete e colheita por talhão)
        uso_equipamentos    (22.575 linhas — diário de uso de máquinas/equipamentos)
        ↓  consultado DIRETAMENTE (sem passo de conversão)
mcp_server/farm_stats.py — servidor MCP "farm-stats":
        17 ferramentas de consulta: busca exata, filtro, agregado, texto livre
        ↓
Hermes (agente de IA) — decide qual ferramenta usar, segue as regras da
        skill farm-telegram, faz uma segunda passada de verificação antes
        de responder
        ↓
Bot do Telegram — entrega a resposta final para o funcionário

## repositório

- **`data/`** Aqui que as planilhas originais da fazenda (do jeito que saem do sistema, meio bagunçadas) chegam antes de qualquer organização. Ninguém mexe nelas diretamente depois — servem só de matéria-prima.r

- **`scripts/`** Cada script sabe ler um tipo de planilha (um lê pesagem, outro lê frete, outro lê uso de trator) e guarda tudo certinho num arquivador grande (o banco de dados Postgres). Também tem um script "detetive" (`detect_and_load_xlsx.py`) que olha pra planilha antes de decidir qual dos outros scripts deve analisar ela — assim ele nunca entrega o trabalho pro script errado.

- **`mcp_server/`** Depois que tudo está arquivado, alguém precisa saber exatamente onde procurar cada coisa. É essa pasta (`farm_stats.py`) que sabe fazer perguntas certeiras ao arquivador: "me dá a ficha do romaneio 14683", "soma todas as horas que o trator tal trabalhou" Ela nunca inventa resposta — ou acha o que foi pedido, ou diz claramente "não achei".

- **`agent/`** serve como um caderno de regras do assistente que conversa com as pessoas (ele se chama Hermes). Tem escrito ali: "se alguém perguntar um número de romaneio, pergunte pra bibliotecária desse jeito", esse tipo de instrução.

- **`telegram_bot/`** — É quem fica esperando mensagem chegar no Telegram, leva a pergunta até o assistente (Hermes), espera a resposta, e entrega de volta pra pessoa que perguntou. Só deixa entrar gente que está numa lista de convidados.

- **`docs/`** — é o manual de instrução, tem como tudo funciona, por que certas decisões foram tomadas, como configurar um computador novo do zero.

- **`logs/`** — Toda vez que um script organizador roda, ele escreve aqui o que fez

- **`notes/`** — um log mais antigo de quando este projeto começou

- **`.claude/`** — as regras de segurança para quando um assistente de IA trabalha no código deste projeto

- **`.venv`, `.venv-bot`, `.venv-mcp`** — é comom se fosse três caixas de ferramentas separadas. Cada script usa uma caixa diferente, com só as ferramentas que ele precisa — assim uma ferramenta de um não bagunça o trabalho do outro.

- **`.git`** — Guarda uma cópia de cada mudança que já foi feita no projeto, pra sempre dar pra voltar e ver "como era antes".

- **`gbrain/`** — é uma biblioteca gigante e genérica que já existia. Ela guarda anotações soltas de qualquer assunto e responde perguntas "no chute inteligente", lendo o que parece mais parecido com a pergunta. Esse chute não funciona bem pra ficha exata tipo "romaneio 14683" (testamos e às vezes ela trazia a ficha errada, ou dizia que achou algo que não existia) — por isso construímos a nossa própria bibliotecária (`mcp_server/`), que nunca chuta. O `gbrain` continua ligado, só que agora só seria chamado se um dia a fazenda guardar algo que não é ficha, tipo ata de reunião em texto corrido.

- **`gbrain-farm-pages/`** — é uma pilha de resumos em papel que a fábrica criava especialmente pra entregar pra essa biblioteca, porque ela só sabe ler texto corrido, não sabe abrir o arquivador do Postgres sozinha. Cada ficha de pesagem/frete virava uma folha de resumo só pra biblioteca conseguir "ler".

## Por que o gbrain não é a melhor solução para esses dados

O gbrain é uma ferramenta de busca semântica de propósito geral. Ele faz bastante sentido como um “cérebro da empresa”, armazenando coisas como notas, transcrições de reunião, contratos e documentos em texto livre.

Os dados da fazenda são praticamente o oposto disso. São dados relacionais, com estrutura fixa e campos bem definidos. Um romaneio tem número, placa, motorista e pesos. Um talhão tem área, frete e informações de colheita.

Em um teste registrada em `docs/AUDIT.md`, encontrei os seguintes problemas:

* **A busca semântica pode esconder uma correspondência exata.** Ao pesquisar por “Romaneio 15064”, por exemplo, outros romaneios apareciam antes do 15064.
* **A busca retornava resultados mesmo quando o ID não existia.** Um romaneio ou uma placa inexistente ainda podia gerar resultados com pontuação alta, sem deixar claro que não havia nenhuma correspondência real.
* **O gbrain não é feito para agregações.** Perguntas como “qual foi o maior?” ou “qual foi o menor?” erraram quatro de cinco vezes. Isso acontece porque o sistema ordena resultados pela semelhança do texto, não pelo valor numérico. Contagens, somas e médias também não são o tipo de operação que ele foi projetado para fazer.
* **Cada linha precisava ser transformada em texto.** Como o gbrain indexa texto livre, cada registro do Postgres precisava virar uma página em Markdown criada artificialmente pelo `scripts/generate_gbrain_pages.py`. Na prática, isso criava uma segunda cópia dos dados, que precisava ser gerada e importada novamente sempre que algo mudava.

### Usando o gbrain como camada de dados das tabelas

Pontos positivos:

- Permite fazer perguntas mais abertas em linguagem natural.
- Já estava integrado ao sistema e funcionando como servidor MCP.
- Pode voltar a ser útil caso apareçam conteúdos não estruturados, como atas, contratos ou relatórios em texto livre.

Pontos negativos:

- Não é confiável para buscas por IDs exatos, como ficou demonstrado na auditoria.
- Não consegue fazer contagens, somas, médias ou encontrar máximos e mínimos de forma confiável.
- Exige uma etapa manual de sincronização para cada tabela, que foi exatamente o que causou o problema com uso_equipamentos.
- Gera custo de embedding sempre que as páginas precisam ser criadas e reimportadas.
- Duplica os dados entre o Postgres e as páginas do gbrain, criando o risco de as duas versões ficarem dessincronizadas.

## Conclusão prática

Para os dados que existem hoje, que são totalmente tabulares, a abordagem direta é melhor nos pontos que realmente importam para esse projeto.

O gbrain continua conectado ao sistema, mas passa a ficar reservado para o momento em que houver conteúdo realmente não estruturado, como atas de reunião, contratos ou relatórios escritos em texto livre.

## Solução do projeto usando SQL

A arquitetura que foi implementada na seção anterior já é, na prática, a solução em SQL para o problema.

1. **Todas as consultas são fixas e parametrizadas.** Nenhuma instrução SQL é montada concatenando texto enviado pelo usuário. Valores como número de romaneio ou nome de motorista sempre entram por parâmetros, utilizando `%s` e a lista de parâmetros do driver, nunca diretamente dentro da string da consulta.
2. **Nomes de tabelas, colunas e operações vêm apenas de listas previamente definidas no código.** Isso pode ser feito por meio de dicionários em Python ou tipos `Literal`. Nenhuma string arbitrária enviada pelo usuário pode decidir qual tabela, coluna ou operação será usada. Dessa forma, o sistema não precisa disponibilizar SQL livre e não consegue executar uma consulta que não tenha sido previamente aprovada.
3. **Toda busca informa explicitamente se encontrou ou não uma correspondência.** As respostas seguem um contrato como `{"match_found": true/false, ...}`. Isso evita que um registro inexistente seja confundido com um resultado vazio ou com alguma correspondência aproximada.

Na prática, isso funciona como um pequeno SQL Query Builder restrito e seguro. Também dá para pensar nessa estrutura como uma camada de views ou funções SQL, escrita em Python por conveniência e para se integrar melhor ao protocolo MCP usado pelo Hermes e pelo Claude.