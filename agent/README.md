# agent/ — o cérebro do agente que responde, espelhado para transição de responsabilidade

O bot do Telegram (`telegram_bot/bot.py`) não responde às perguntas
sozinho — ele chama o **Hermes**, uma CLI de agente separada instalada na
máquina (um agente da família OpenClaw, mesma linhagem de outras
implantações de agente do próprio autor do gbrain). O Hermes lê sua
configuração em `~/.hermes/`, totalmente fora deste repositório git,
porque é lá que uma instalação por máquina, com chaves de API/segredos
reais, precisa viver.

Isso é um problema para a transição de responsabilidade (handoff): clonar
este repositório sozinho **não** te dá um agente funcionando. Esta pasta
existe para fechar essa lacuna — ela espelha as partes não secretas e
específicas do projeto da configuração do Hermes para dentro do controle
de versão, para que a próxima pessoa saiba que elas existem e o que
contêm.

## O que tem aqui

- **`hermes-skill/farm-telegram/SKILL.md`** — um espelho de
  `~/.hermes/skills/farm-telegram/SKILL.md`, a skill que o Hermes carrega
  para cada pergunta do Telegram (`hermes chat -s farm-telegram`, veja
  `telegram_bot/ask_hermes.py`). É aqui que as regras de comportamento de
  fato vivem: como formular respostas para um leitor não técnico, qual
  das três ferramentas MCP usar para qual tipo de pergunta (espelha o
  `CLAUDE.md` deste repositório), o contrato de citação, e a regra de
  fundamentação. **Se você quiser mudar como o bot responde ou apresenta
  as coisas, este arquivo (tanto a cópia aqui quanto a versão em uso em
  `~/.hermes/skills/farm-telegram/`) é onde isso vive — não em
  `telegram_bot/bot.py`.**
- **`hermes-mcp-servers.example.yaml`** — uma cópia sanitizada do bloco
  `mcp_servers:` de `~/.hermes/config.yaml` (sem segredos — só quais três
  servidores MCP o Hermes tem permissão de chamar e quais ferramentas em
  cada um estão habilitadas). Chaves de API reais e outras configurações
  específicas da máquina ficam só em `~/.hermes/config.yaml`.

## O que deliberadamente NÃO está aqui

- O próprio Hermes (o binário/instalação) — uma ferramenta separada, não
  vendorizada, mesmo raciocínio de por que o `gbrain` também não é
  vendorizado neste repositório (veja o `README.md` principal).
- O `~/.hermes/config.yaml` completo — ele carrega chaves de API e outros
  segredos junto com o bloco de servidores MCP que é seguro espelhar.
- Qualquer estado de execução do Hermes (`~/.hermes/state.db`, histórico
  de sessões, memórias, tokens de autenticação) — específico da máquina,
  não configuração do projeto.

## Configurando o Hermes em uma máquina nova

1. Instale o Hermes (veja a documentação dele — fora do escopo deste
   repositório).
2. Copie `hermes-skill/farm-telegram/SKILL.md` (desta pasta) para
   `~/.hermes/skills/farm-telegram/SKILL.md` na máquina nova.
3. Combine o conteúdo de `hermes-mcp-servers.example.yaml` com
   `~/.hermes/config.yaml`, corrigindo os três caminhos `command:` para
   apontar para onde você de fato clonou `gbrain` e
   `fazenda-continental-data`.
4. Preencha as chaves de API reais que o Hermes precisa diretamente em
   `~/.hermes/config.yaml` (nunca copie essas chaves para este
   repositório).
5. Verifique: `hermes chat -s farm-telegram -t
   gbrain,farm-stats,gbrain-search-safe -q "pergunta de teste"` a partir
   da raiz do repositório deve retornar uma resposta, não um erro de
   conexão de ferramenta.

## Um cuidado encontrado durante a revisão de 2026-07-10

Os três caminhos `command:` em `~/.hermes/config.yaml` foram encontrados
apontando para uma localização antiga
(`/Users/giacomosantos/gbrain/...` e
`/Users/giacomosantos/fazenda-continental-data/...`) que não existia
mais depois que este espaço de trabalho foi movido para
`~/R.P. fazenda continetal/`. Isso significava que o Hermes não
conseguia de fato iniciar nenhum dos três servidores MCP — corrigido no
mesmo dia (veja `docs/PROJECT_LOG.md`). Se o bot algum dia parar de
responder silenciosamente depois de uma mudança de local do repositório,
essa é a primeira coisa a verificar.
