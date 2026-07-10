# Configurando este repositório em uma máquina nova

Clonar este repositório te dá o código. Isso **não** te dá um sistema
funcionando — várias coisas das quais ele depende vivem fora do git de
propósito (dados reais da fazenda são sensíveis/PII; bancos de dados,
venvs e segredos não pertencem ao controle de versão). Este documento é o
checklist para ir de um clone novo até uma resposta funcionando.

## O que precisa existir antes de qualquer coisa aqui ser útil

- **Postgres**, rodando, acessível em
  `postgresql+psycopg2://localhost/gbrain_dev` (ou defina `FARM_STATS_DSN`
  / edite o `DEFAULT_DB_URL` dos scripts de carga para apontar para outro
  lugar). O próprio banco `gbrain_dev` precisa já existir
  (`createdb gbrain_dev`) — os scripts de carga criam suas próprias
  tabelas dentro dele (`CREATE TABLE IF NOT EXISTS`), mas não o banco.
- **`gbrain`** (opcional) — `pesagens`/`fretes_colheita`/`uso_equipamentos`
  são consultadas diretamente pelas ferramentas do `farm-stats` e nunca
  chamam o gbrain; ele só é necessário se este projeto vier a buscar
  conteúdo genuinamente não estruturado no futuro (veja `docs/USAGE.md`).
  Se for usar, este repositório apenas *se conecta* a ele
  (`~/R.P. fazenda continetal/gbrain`), não o instala nem o configura.
- **A CLI `hermes`**, instalada e configurada — necessária tanto para uso
  interativo quanto porque o bot do Telegram chama
  `hermes chat -s farm-telegram` por baixo dos panos (veja
  `agent/README.md` para como configurar o Hermes para este projeto).
- **Python 3.9+ e 3.12+** disponíveis (`python3` e `python3.12` no PATH)
  — os scripts do pipeline e os dois servidores MCP/bot usam venvs
  diferentes de propósito (veja abaixo).
- **Arquivos reais de exportação GSB/fazenda** (`data/*.csv`, `*.xlsx`) —
  fora do git, não estão no repositório. Você precisa das suas próprias
  cópias; nada para carregar já vem junto com o código.

## Passos

```bash
git clone git@gitlab.com:guac-co-group/fazenda-continental.git
cd fazenda-continental
```

**1. Rode o script de instalação.** `scripts/setup.sh` encadeia tudo
abaixo que pode de fato ser automatizado — verifica se os pré-requisitos
estão no PATH, cria os três venvs e instala suas dependências,
verifica/cria o banco `gbrain_dev`, e (se encontrar arquivos já em
`data/`) roda os carregadores certos para cada arquivo (`.csv` sempre vai
para `load_pesagem_csv.py`; cada `.xlsx` é roteado automaticamente pelo
`scripts/detect_and_load_xlsx.py`, que detecta o carregador certo pelas
colunas do próprio arquivo). Não há mais passo de geração/importação de
páginas — as tabelas ficam consultáveis assim que carregadas. Seguro
para reexecutar.
```bash
./scripts/setup.sh
```

**Ele deliberadamente NÃO:**
- **Roda o `gbrain init` para você.** Esse é um assistente interativo que
  pede suas próprias chaves de API (ZeroEntropy/Anthropic/etc) —
  automatizar cegamente uma etapa que precisa dos segredos de alguém é o
  mesmo erro que fixar um token no código. Rode você mesmo, uma vez, em
  **modo Postgres/Supabase** — não `--pglite` (o modo embutido do
  gbrain, sem servidor): o `farm-stats` se conecta diretamente ao mesmo
  banco Postgres via `psycopg2`, o que só funciona se o gbrain estiver
  de fato rodando contra um servidor Postgres real:
  ```bash
  gbrain init --url postgresql://localhost/gbrain_dev
  ```
- **Busca ou fabrica dados reais da fazenda.** `data/*.csv`/`*.xlsx`
  ficam fora do git de propósito (PII — nomes de motoristas, placas,
  documentos de clientes). Se `data/` estiver vazio quando você rodar o
  script, ele pula a etapa de carga e avisa você disso. Coloque suas
  exportações reais do GSB e reexecute.
- **Instala ou vendoriza o próprio `gbrain`.** É uma aplicação separada e
  completa por design — veja a própria documentação dele sobre
  implantações multi-projeto de "cérebro da empresa" (company brain). O
  script só verifica se está no PATH e já inicializado.

**2. Registre o servidor MCP.** O `.mcp.json` está versionado e já
aponta para o script certo usando `${CLAUDE_PROJECT_DIR}`, então isso
funciona independentemente de onde você clonou o repositório — nada para
editar. Inicie uma sessão do Claude Code na raiz do repositório e rode
`/mcp` para confirmar que `farm-stats` aparece como conectado.

**3. Bot do Telegram** (opcional — só se você quiser o bot, não apenas
acesso interativo via Claude Code):
```bash
cd telegram_bot
cp .env.example .env
```
Preencha o `.env` você mesmo (não cole segredos numa conversa com um
assistente de IA, incluindo este):
- `TELEGRAM_BOT_TOKEN` — obtido no `@BotFather` no Telegram (`/newbot`)
- `ALLOWED_TELEGRAM_USER_IDS` — deixe vazio no início, rode `./run.sh`,
  mande uma mensagem para o bot, e a resposta de rejeição vai incluir seu
  ID numérico de usuário do Telegram. Adicione aqui e reinicie.

```bash
./run.sh
```

## Verificando que funciona de fato

Faça uma pergunta que você consiga checar de forma independente contra a
exportação bruta, por exemplo o peso de um número de Romaneio específico
— e confira a resposta diretamente contra o arquivo de origem. Tente
também um ID que não existe (ex.: um número de Romaneio bem fora da faixa
real) — a resposta deve vir com um "sem resultado" explícito
(`match_found: false`), não uma resposta com aparência fabricada. Veja o
CLAUDE.md para a tabela completa de qual ferramenta responde qual tipo
de pergunta, e `docs/USAGE.md` para o fluxo completo de como uma
resposta é construída.
