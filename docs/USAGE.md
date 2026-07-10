# Fazendo perguntas ao sistema

Os dados da fazenda (`pesagens`, `fretes_colheita`, `uso_equipamentos`)
ficam consultáveis através das ferramentas MCP do `farm-stats` assim que o
servidor está conectado (veja o `README.md` principal para o pipeline que
leva os dados até o Postgres). Este documento é sobre o outro lado: como
uma pergunta em linguagem natural vira uma resposta.

## Como uma resposta é de fato construída (desde 2026-07-10)

```
1. Você faz uma pergunta (Telegram, Claude Code, ou hermes chat direto)
        ↓
2. O agente (Hermes ou Claude) reconhece o tipo de pergunta e escolhe a
   ferramenta farm-stats certa — busca exata, filtro, agregado, ou texto
   livre (regras completas em CLAUDE.md / agent/hermes-skill/farm-telegram/SKILL.md)
        ↓
3. A ferramenta roda um SELECT parametrizado e determinístico direto no
   Postgres (nunca ranking semântico, nunca SQL livre)
        ↓
4. O agente lê o resultado (um registro, uma lista, ou um número) e
   escreve a resposta, citando o identificador de origem
```

Não há mais um passo de busca semântica/RAG para essas três tabelas — o
gbrain foi removido desse caminho porque a busca dele, testada
(`docs/AUDIT.md`), rankeava por similaridade textual, não por
correspondência exata ou valor numérico, e não conseguia agregar. Uma
ferramenta determinística (`WHERE numero_romaneio = X`, `SUM(...)`, etc.)
não tem essa ambiguidade: ou encontra a linha certa, ou retorna
`match_found: false` de forma explícita.

## Qual ferramenta responde qual tipo de pergunta

- **ID exato** (Romaneio, Talhão) → `pesagem_get` / `frete_get`.
- **Uso de equipamento/máquina** (sem ID único de linha) →
  `uso_equipamentos_search`.
- **Contagem / soma / média / mínimo / máximo** → as ferramentas
  `*_count` / `*_aggregate` / `*_extremes` / `*_group_counts` /
  `*_distinct_count` de cada tabela.
- **Texto livre nas observações** → `*_search_observacao`.

Veja `CLAUDE.md` para a tabela completa e `docs/AUDIT.md` para a
evidência por trás dessas escolhas.

## Boas práticas ao perguntar

**1. Seja específico.** IDs, datas, nomes exatos de motorista/equipamento
levam direto à ferramenta certa. Perguntas muito vagas ("me conte sobre a
fazenda") não mapeiam para nenhuma ferramenta determinística — hoje, sem
identificador ou filtro nenhum, o sistema não tem como responder algo
assim com fundamento nos dados.

**2. Peça específicos que não podem ser adivinhados.** Pesos, datas,
porcentagens ou IDs exatos deixam claro que a resposta precisa vir de uma
consulta real, não de conhecimento geral.

**3. Peça as fontes quando estiver em dúvida.** Toda resposta deveria
citar um romaneio, talhão, ou identificador de equipamento (contrato de
citação no SKILL.md do Hermes). Se uma resposta não cita nada
específico, vale perguntar de onde veio o número.

**4. Verifique no início de uma sessão** (uso interativo via Claude
Code). Rode `/mcp` logo após abrir uma nova sessão e confirme que
`farm-stats` aparece como conectado antes de confiar nele.

## O que o gbrain ainda faz neste projeto

O gbrain continua conectado como servidor MCP separado, reservado para
conteúdo genuinamente não estruturado que venha a existir no futuro
(atas de reunião, contratos, relatórios em texto livre) — não para as
três tabelas estruturadas que já existem hoje. Se algum dia isso mudar,
esta seção precisa ser reescrita.

## Limitação conhecida: sem fallback para SQL

O CLAUDE.md deste repositório proíbe SQL/psql direto contra
`pesagens`/`fretes_colheita`/`uso_equipamentos` de forma incondicional —
mesmo para contagens/totais exatos, use as ferramentas do `farm-stats`
(que já cobrem esses casos com precisão, ao contrário do gbrain antigo).
`psql` via Bash é bloqueado também no nível de permissão
(`.claude/settings.json`) como reforço estrutural, não só uma regra em
texto.
