# CLAUDE.md

Este repositório tem dados reais da fazenda (registros de pesagem, frete e
uso de equipamentos da Fazenda Continental), consultados diretamente via
as ferramentas MCP do `farm-stats` — nenhuma dessas três tabelas passa
mais pelo `gbrain` (veja `docs/AUDIT.md` para a evidência e o histórico
dessa decisão). O gbrain (`~/R.P. fazenda continetal/gbrain`) continua
conectado como servidor MCP, reservado para conteúdo genuinamente não
estruturado no futuro (atas, contratos) — não para estas três tabelas.
Veja o README.md para o diagrama do pipeline.

## Regras

- **Nunca consulte `pesagens`/`fretes_colheita`/`uso_equipamentos` via SQL
  bruto, `psql`, ou qualquer outro caminho livre de banco de dados**, para
  nenhuma pergunta sobre os dados da fazenda. Use as ferramentas MCP do
  `farm-stats` — sem exceções, não é um "padrão com exceções". O `psql`
  bruto também é bloqueado no nível de permissão (`.claude/settings.json`)
  como reforço. As únicas exceções legítimas: `scripts/load_*.py` +
  `scripts/detect_and_load_xlsx.py` (o próprio pipeline de carga, não uma
  forma de responder perguntas de conteúdo) e `mcp_server/farm_stats.py`
  (ferramentas fixas baseadas em enum, não uma via de escape para SQL).
  `scripts/generate_gbrain_pages.py` está aposentado — não faz mais parte
  do pipeline em uso, ver aviso no topo do próprio arquivo.
- **Perguntas de ID exato**:
  - Romaneio → `pesagem_get(numero_romaneio)`.
  - Talhão/campo (Local, ex.: BL.xxx ou P.xx) → `frete_get(local)`.
  - Ambas retornam `{"match_found": true, "record": {...}}` ou
    `{"match_found": false, "message": ...}` — um `WHERE` direto e
    determinístico, não busca semântica.
- **`uso_equipamentos` não tem um ID único de linha** (é um diário de uso;
  a chave natural é um hash da linha inteira, só serve para deduplicar,
  nunca para consultar). Perguntas sobre uso de equipamento/máquina →
  `uso_equipamentos_search` (filtro por número de equipamento,
  funcionário, serviço, fase e/ou intervalo de datas).
- **Perguntas de contagem/soma/média/mínimo/máximo** sobre `pesagens`,
  `fretes_colheita` ou `uso_equipamentos` → as ferramentas MCP do
  `farm-stats`. Ferramentas: `pesagens_count`, `pesagens_aggregate`,
  `pesagens_extremes`, `pesagens_date_range`, `pesagens_group_counts`,
  `pesagens_distinct_count`, `fretes_aggregate`, `uso_equipamentos_count`,
  `uso_equipamentos_aggregate`, `uso_equipamentos_extremes`,
  `uso_equipamentos_group_counts`, `uso_equipamentos_distinct_count`.
- **Perguntas narrativas/texto livre** (algo mencionado no campo
  Observação de `pesagens` ou `uso_equipamentos`, sem um ID exato) →
  `pesagens_search_observacao` / `uso_equipamentos_search_observacao`
  (busca por substring, case-insensitive). Não existe mais uma rota de
  busca semântica de fallback para estas três tabelas — se nenhuma
  ferramenta acima responde a pergunta, diga isso explicitamente em vez
  de tentar o gbrain.
- **Verifique antes de responder.** Antes de apresentar um resultado como
  resposta a uma pergunta de ID/nome específico, confirme que o campo de
  romaneio/placa/talhão/equipamento do próprio resultado bate literalmente
  com o que foi perguntado. Se nada bater, diga isso explicitamente
  ("nenhum registro encontrado para o Romaneio X") — nunca responda com o
  resultado mais próximo mesmo assim.
- **Verifique `match_found`, não a ausência de resultados.** Toda
  ferramenta que retorna um dict carrega esse campo — inclusive
  `pesagem_get`/`frete_get` no caso de sucesso (`{"match_found": true,
  "record": {...}}`), não só no de falha. Verifique sempre esse campo em
  vez de tratar um dict/lista vazia como ambígua. `pesagens_count` /
  `pesagens_aggregate` / `fretes_aggregate` / `uso_equipamentos_count` /
  `uso_equipamentos_aggregate` não mudam (`0`/`None` já são inequívocos
  para esses casos).

## Regra prática

Toda pergunta sobre `pesagens`, `fretes_colheita` ou `uso_equipamentos`
mapeia para uma ferramenta `farm-stats` determinística: busca exata
(`*_get`/`uso_equipamentos_search`), agregado
(`*_count`/`*_aggregate`/`*_extremes`/`*_group_counts`/`*_distinct_count`),
ou texto livre (`*_search_observacao`). O gbrain só entra em cena se a
pergunta for sobre conteúdo fora dessas três tabelas.

Veja `docs/AUDIT.md` para os testes e o histórico por trás dessas regras
e `docs/SETUP.md` para colocar um clone novo para rodar.
