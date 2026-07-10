# Fazenda Continental — Pipeline de Dados da Fazenda

Dados brutos da fazenda + o pipeline de carga que alimenta o Postgres
consultado diretamente pelas ferramentas MCP do `farm-stats`. Sucessor do
repositório original `fazenda-continental-internship` — este aqui leva
adiante apenas as peças essenciais (dados brutos, carregadores, ferramentas
de consulta); o protótipo de busca local descontinuado (fastembed/
sentence-transformers, tabela `documentos` separada) não foi trazido.

## Pipeline

```
data/*.csv, *.xlsx  (exportações brutas da fazenda)
        ↓  scripts/load_pesagem_csv.py, load_fretes_xlsx.py, load_equipamentos_xlsx.py
           (o roteamento de .xlsx é automático — scripts/detect_and_load_xlsx.py)
gbrain_dev Postgres: tabelas pesagens, fretes_colheita, uso_equipamentos
        ↓  consultado diretamente (sem passo de exportação/importação)
mcp_server/farm_stats.py  →  servidor MCP "farm-stats":
        pesagem_get / frete_get                      (busca exata por chave)
        uso_equipamentos_search                       (filtro — diário de uso, sem ID único)
        pesagens_count/aggregate/extremes/...          (agregados de pesagens/fretes)
        uso_equipamentos_count/aggregate/extremes/...  (agregados de uso de equipamento)
        *_search_observacao                            (busca textual, ILIKE)
        ↓
Hermes / Claude Code (via MCP)
```

O `gbrain` (`~/R.P. fazenda continetal/gbrain`) continua conectado como
servidor MCP separado, mas **não** faz mais parte deste pipeline — as três
tabelas acima são consultadas diretamente, sem passar por ele. Isso
substitui um desenho anterior (linha do Postgres → página markdown →
`gbrain import` → busca semântica) que o próprio `docs/AUDIT.md` mostrou
pouco confiável para os tipos de pergunta mais comuns aqui (ID exato,
agregados) e que exigia lembrar de sincronizar manualmente cada tabela
nova — ver `docs/PROJECT_LOG.md` (entrada de 2026-07-10) para o histórico
completo. `scripts/generate_gbrain_pages.py` fica no repositório só como
referência, aposentado (aviso no topo do próprio arquivo). O gbrain segue
reservado para conteúdo genuinamente não estruturado no futuro (atas,
contratos) — veja CLAUDE.md para as regras de quando usar qual ferramenta.

## Estrutura

- `data/` — exportações brutas de dados da fazenda (xlsx, csv)
- `scripts/` — os scripts do pipeline (`load_pesagem_csv.py`,
  `load_fretes_xlsx.py`, `load_equipamentos_xlsx.py`,
  `detect_and_load_xlsx.py` — detecta qual carregador usar em cada `.xlsx`
  pelas colunas do cabeçalho, não pelo nome do arquivo), além de
  `db_upsert.py` (helper de upsert compartilhado), `logging_setup.py`
  (configuração de log compartilhada), `setup.sh` (encadeia tudo que um
  clone novo consegue automatizar — veja `docs/SETUP.md`), e
  `golden_check.py` / `golden_cron.sh` (um harness de regressão de
  "respostas padrão-ouro" — roda um conjunto fixo de perguntas conhecidas
  pelo mesmo caminho `ask_hermes` usado em produção e checa as respostas
  contra o gabarito, para pegar alucinação/desvio ao longo do tempo;
  `golden_cron.sh` é um wrapper de cron que fica em silêncio quando passa
  e reporta quando falha). `generate_gbrain_pages.py` está aposentado —
  ver aviso no topo do arquivo
- `mcp_server/` — `farm_stats.py`, o servidor MCP `farm-stats`: busca
  exata por chave (`pesagem_get`, `frete_get`), filtro/busca em
  `uso_equipamentos`, agregados das três tabelas, e busca textual
  (`*_search_observacao`) — veja CLAUDE.md para o roteamento completo.
  `serve.sh` é o wrapper de inicialização (resolve os caminhos a partir da
  própria localização, então o diretório de trabalho não importa).
  `gbrain_search_safe.py` continua no repositório (não registrado mais —
  pode voltar a ser útil se o gbrain buscar conteúdo não estruturado no
  futuro)
- `telegram_bot/` — `bot.py`, um front-end de Telegram que responde cada
  mensagem via `ask_hermes.py` (chama a CLI do agente `hermes` com a skill
  `farm-telegram` — veja `agent/README.md`), com uma checagem em duas
  passadas que retém a resposta se uma segunda passada independente a
  contradisser; apenas IDs de usuário do Telegram na lista de permissão,
  já que os dados são sensíveis (PII). `run.sh` é o script de
  inicialização; copie `.env.example` para `.env` (fora do git) e
  preencha o token do bot — veja CLAUDE.md para saber como conseguir um
- `agent/` — um espelho versionado da configuração do agente Hermes que
  de fato responde às perguntas (a cópia real vive fora do git, por
  máquina, em `~/.hermes/`) — as regras de apresentação/escolha de
  ferramenta que o bot segue, e como reproduzir a configuração em uma
  máquina nova; veja `agent/README.md`
- `logs/` — `pipeline.log`, um registro cronológico de cada execução de
  script (fora do git — mesma sensibilidade de PII que `data/`)
- `VISAO_GERAL.md` (na raiz do repositório) — visão consolidada do
  projeto: como funciona, por que o gbrain foi trocado por ferramentas
  diretas, pontos positivos/negativos, explicação de cada pasta em
  linguagem simples. Leia este primeiro se está chegando agora.
- `docs/` — documentação estendida: `docs/USAGE.md` (como o
  sistema responde perguntas hoje), `docs/SETUP.md` (como colocar um
  clone novo funcionando do zero em uma máquina nova), e `docs/AUDIT.md`
  (os testes/evidências por trás das regras de escolha de ferramenta do
  CLAUDE.md)
- `notes/` — diário do estágio, trazido do repositório original
- `requirements.txt` — dependências Python fixadas para `scripts/` (venv
  Python 3.9)
- `.mcp.json` — registra o servidor MCP `farm-stats` para este projeto
- `CLAUDE.md` — regras de comportamento sucintas para sessões do Claude
  Code neste repositório (sem fallback improvisado para SQL; ferramentas
  do farm-stats para tudo — busca exata, agregados, texto livre); veja
  `docs/AUDIT.md` para entender o porquê
- `.claude/settings.json` — lista de permissões negadas em nível de
  projeto, que reforça uma das regras do CLAUDE.md de forma estrutural
  (`psql` via Bash), não só por instrução

## Instalação

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

O servidor MCP `farm-stats` precisa de Python >=3.10 (o `.venv` do
pipeline em si é 3.9), então ele roda em um venv separado:

```
python3.12 -m venv .venv-mcp
source .venv-mcp/bin/activate
pip install -r mcp_server/requirements.txt
```

## Reexecutando o pipeline

Os carregadores são seguros para reexecutar sobre os mesmos dados ou
dados atualizados. Todos fazem upsert numa chave natural
(`numero_romaneio` para pesagens, `local` para fretes_colheita, um hash
da linha inteira para `uso_equipamentos` — é um diário de uso, sem coluna
que identifique uma linha unicamente) via `db_upsert.py` — reexecutar
sobre um arquivo com linhas já presentes no Postgres atualiza essas
linhas em vez de duplicá-las. Não há passo de exportação/importação
depois da carga — as tabelas ficam disponíveis para consulta assim que
carregadas.

Veja o CLAUDE.md para a regra de sempre usar as ferramentas MCP do
`farm-stats` (nunca SQL bruto) para responder perguntas sobre esses
dados, e `docs/USAGE.md` para entender como uma resposta é de fato
construída.

## Logging

Os scripts do pipeline registram log tanto no console quanto em
`logs/pipeline.log` (via `scripts/logging_setup.py`), então o estado de
uma execução — linhas lidas/upsertadas, avisos (ex.: uma data que não
pôde ser interpretada), erros, contagem de linhas em cada etapa — fica
registrado cronologicamente entre os scripts, não só visível enquanto se
observa o terminal ao vivo.
