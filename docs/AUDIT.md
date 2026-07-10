# Auditoria de precisão de busca/ferramentas

Evidências por trás das regras de escolha de ferramenta no CLAUDE.md.
Achados de testes com as ferramentas search/query do gbrain e a
ferramenta MCP `farm-stats` contra as exportações brutas
`data/*.csv`/`*.xlsx`, mais recentemente em 2026-07-08.

## O `query` do gbrain enterra correspondências exatas sob quase-correspondências semânticas

Uma auditoria de 20 perguntas (2026-07-08) descobriu que o ranking
semântico do `query` pode enterrar a correspondência exata sob registros
não relacionados com redação parecida — ex.: consultar "Romaneio 15064"
retornou outros romaneios nos resultados principais, não o 15064 em si.

## O `search` do gbrain, chamado diretamente, fabrica correspondências para IDs inexistentes

Testes no mesmo dia descobriram que a ferramenta `search` bruta do
gbrain é pior do que a auditoria do `query` acima sugeria: para um ID que
não existe em lugar nenhum dos dados (ex.: "Romaneio 99999", uma placa
inexistente "ZZZ9999"), ela ainda retorna vários resultados marcados
`"evidence": "keyword_exact"` com pontuações altas (~0,80+) e nenhum
sinal de que nada de fato correspondeu.

Isso é reproduzível, e foi confirmado que *não* é um bug do motor de
busca do gbrain: `gbrain call search` (a mesma ferramenta subjacente,
chamada localmente via CLI) retorna corretamente `[]` para a consulta
idêntica. A falha está na fiação da ferramenta MCP especificamente para
esta sessão — o `gbrain-search-safe`
(`mcp_server/gbrain_search_safe.py`) passa pelo caminho confiável da CLI
em vez disso, e retorna um `{"match_found": false, ...}` explícito.

Também encontrado: mesmo quando a correspondência exata *está* em algum
lugar do conjunto de resultados, o resultado mais bem ranqueado do
`search` bruto nem sempre é a correspondência de fato — cerca de 29% das
buscas de ID exato testadas (2/7 em uma rodada) tiveram a correspondência
verdadeira ranqueada em #2 ou pior, atrás de um registro não relacionado
com pontuação mais alta.

## O search/query do gbrain não consegue responder perguntas numéricas ou agregadas de forma confiável

Perguntas de superlativo (maior/menor/mais/menos) e perguntas de
contagem/soma/média: o `search`/`query` do gbrain ranqueiam por
similaridade textual/semântica, não por valor numérico ou agregação em
todo o corpus, então foram encontrados errados 4 vezes em 5 em perguntas
de máximo/mínimo (auditoria, 2026-07-08) e não conseguem responder
contagem/soma/média de jeito nenhum. O `farm-stats`
(`mcp_server/farm_stats.py`) roda agregados SQL exatos e parametrizados
diretamente contra o Postgres, em vez disso.

## Precisão do farm-stats

Cada saída de ferramenta do `farm-stats` foi conferida cruzadamente
contra um cálculo independente em pandas sobre o CSV/XLSX bruto (não
através das tabelas carregadas no Postgres) — 13/13 correspondências
exatas entre contagens, agregados (soma/média/mín/máx), extremos,
contagens por grupo, contagens de distintos, e faixa de datas, incluindo
casos extremos (um campo com apenas 179/400 leituras não nulas, um
filtro que não bate com nenhuma linha). Também foram verificados os
filtros `produto`/`possui_romaneio` adicionados depois (média de
peso_liquido_seco_kg onde possui_romaneio=false: 12895,377358490567,
correspondência exata contra um cálculo independente em pandas).

## 2026-07-10 — gbrain removido como camada de dados para as três tabelas

A tabela `uso_equipamentos` (22.575 linhas, carregada em 08/07) ficou
sem nenhum caminho de consulta por dias: `scripts/generate_gbrain_pages.py`
só lia `pesagens`/`fretes_colheita`, e `scripts/setup.sh` rodava
`load_fretes_xlsx.py` cegamente em todo `.xlsx` de `data/` (foi isso que
quebrou quando o arquivo de equipamentos apareceu — o carregador
dedicado, `load_equipamentos_xlsx.py`, foi escrito na hora para parar o
erro, mas nunca foi ligado de volta ao `setup.sh` nem ao passo de
geração de páginas). Ou seja: os dados entravam no Postgres, mas nunca
viravam página gbrain e não tinham ferramenta `farm-stats`
correspondente — invisíveis para o bot.

Combinado com os achados acima (busca semântica enterra ID exato, busca
bruta fabrica correspondência, nenhum dos dois agrega), a decisão foi
parar de usar o gbrain como camada de armazenamento/busca para
`pesagens`, `fretes_colheita` e `uso_equipamentos`, e substituir por
ferramentas MCP diretas e determinísticas (`mcp_server/farm_stats.py`):
busca por chave exata (`pesagem_get`, `frete_get`), filtro
(`uso_equipamentos_search`), agregados
(`*_count`/`*_aggregate`/`*_extremes`/`*_group_counts`/`*_distinct_count`)
e texto livre via SQL `ILIKE` (`*_search_observacao`).

Isso resolve as duas classes de problema ao mesmo tempo: um `WHERE`
indexado direto não tem os modos de falha de ranking/fabricação já
documentados acima, e como não existe mais um passo separado de
"gerar página + importar no gbrain" por tabela, a classe de bug que
deixou `uso_equipamentos` invisível deixa de existir — uma tabela nova
precisa de uma ferramenta nova, não de um passo de sincronização
manual e esquecível. `scripts/setup.sh` também foi corrigido para rotear
cada `.xlsx` pelo carregador certo automaticamente
(`scripts/detect_and_load_xlsx.py`, que detecta pelas colunas do
cabeçalho, não pela extensão do arquivo).

O gbrain continua conectado como servidor MCP, reservado para quando (se)
existir conteúdo genuinamente não estruturado (atas, contratos). Ver
`VISAO_GERAL.md` (raiz do repositório) para a explicação completa
(arquitetura, prós/contras, próximos passos).
