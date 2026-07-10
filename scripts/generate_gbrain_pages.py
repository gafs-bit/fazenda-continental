"""
APOSENTADO (2026-07-10) -- não faz mais parte do pipeline em uso. Mantido
só como referência/template (a lógica de slugify/write_page pode servir de
base se o gbrain vier a indexar conteúdo genuinamente não estruturado no
futuro). Não reexecute isto contra dados de produção para responder
perguntas -- pesagens/fretes_colheita/uso_equipamentos são consultadas
diretamente pelas ferramentas do farm-stats (mcp_server/farm_stats.py:
pesagem_get, frete_get, uso_equipamentos_*), sem esse passo de conversão.
Ver docs/AUDIT.md e docs/PROJECT_LOG.md (entrada de 2026-07-10) para o
porquê: o gbrain, testado, não era confiável para os tipos de pergunta
mais comuns sobre estes dados (ID exato, agregados), e cada tabela nova
exigia lembrar deste passo manual de sincronização -- foi exatamente isso
que deixou `uso_equipamentos` invisível ao bot por um tempo.

Converts rows from `pesagens` and `fretes_colheita` (already loaded into
gbrain_dev by load_pesagem_csv.py / load_fretes_xlsx.py) into gbrain-format
markdown pages, so they can be ingested with `gbrain import <dir>`.

gbrain has no native CSV/DB importer -- it only ingests markdown files with
YAML frontmatter (type/title/tags/slug) plus a body. One page is generated
per row, mirroring the row-level granularity already used by the local
`documentos` embedding prototype (build_embeddings.py).

Output goes OUTSIDE any git repo by default
(~/R.P. fazenda continetal/gbrain-farm-pages) since the rows contain real
driver names, truck plates and client/document numbers -- the same
sensitivity class as data/ (gitignored in this repo). Do not point
--output-dir at a git-tracked location without gitignoring it first.
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from logging_setup import get_logger

DEFAULT_DB_URL = "postgresql+psycopg2://localhost/gbrain_dev"
DEFAULT_OUTPUT_DIR = Path.home() / "R.P. fazenda continetal" / "gbrain-farm-pages"

logger = get_logger("generate_gbrain_pages")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "item"


def yaml_str(value: str) -> str:
    """Quote a string safely for a YAML frontmatter scalar."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_page(output_dir: Path, filename: str, frontmatter: dict, body: str) -> None:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            items = ", ".join(yaml_str(v) for v in value)
            lines.append(f"{key}: [{items}]")
        else:
            lines.append(f"{key}: {yaml_str(value)}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())
    lines.append("")

    path = output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def pesagem_page(row) -> tuple[str, dict, str]:
    quality = row.parametros_qualidade or {}
    umidade = quality.get("UMIDADE")
    impureza = quality.get("IMPUREZA")

    produto = (row.produto or "").strip()
    motorista = (row.nome_motorista or "").strip()
    chegada = row.data_chegada
    chegada_known = pd.notna(chegada)
    chegada_str = f"{chegada:%d/%m/%Y %H:%M}" if chegada_known else "data desconhecida"
    chegada_date_str = f"{chegada:%d/%m/%Y}" if chegada_known else "data desconhecida"

    body_parts = [
        f"Carga de {produto} entregue por {motorista} em {chegada_str}.",
        f"Romaneio {row.numero_romaneio}, placa {row.placa}, tipo de pesagem {row.tipo_pesagem}.",
        f"Peso bruto {row.peso_bruto_kg:.0f} kg, peso tara {row.peso_tara_kg:.0f} kg, "
        f"peso líquido úmido {row.peso_liquido_umido_kg:.0f} kg, "
        f"peso líquido seco {row.peso_liquido_seco_kg:.1f} kg.",
    ]
    if umidade is not None:
        body_parts.append(f"Umidade de {umidade}%.")
    if impureza is not None:
        body_parts.append(f"Impureza de {impureza}%.")
    if row.cliente:
        body_parts.append(f"Cliente: {row.cliente}.")
    if row.local_entrega:
        body_parts.append(f"Local de entrega: {row.local_entrega}.")
    if isinstance(row.observacao, str) and row.observacao.strip():
        body_parts.append(f"Observação: {row.observacao.strip()}.")

    body = " ".join(body_parts)

    title = f"Pesagem {row.numero_romaneio} — {produto} ({chegada_date_str})"
    tags = ["pesagem", slugify(produto), row.tipo_pesagem.lower() if row.tipo_pesagem else "pesagem"]

    frontmatter = {
        "type": "note",
        "title": title,
        "tags": tags,
        "id": f"pesagem-{row.id}",
    }
    if chegada_known:
        frontmatter["date"] = chegada.strftime("%Y-%m-%d")

    filename = f"pesagem-{row.id:04d}-{slugify(motorista)}.md"
    return filename, frontmatter, body


def frete_page(row) -> tuple[str, dict, str]:
    local = (row.local or "").strip()
    municipio = (row.municipio or "").strip()

    body = (
        f"Talhão {local}, área de {row.area_ha:.1f} ha, localizado em {municipio}. "
        f"Frete de R$ {row.frete_reais_saca:.2f} por saca (peso líquido úmido), "
        f"custo de colheita de R$ {row.colheita_reais_ha:.0f} por hectare."
    )

    title = f"Frete e colheita — Talhão {local} ({municipio})"
    tags = ["frete", "colheita", "sorgo", slugify(municipio)]

    frontmatter = {
        "type": "note",
        "title": title,
        "tags": tags,
        "id": f"frete-{row.id}",
    }

    filename = f"frete-{row.id:03d}-{slugify(local)}.md"
    return filename, frontmatter, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Must not be inside a git-tracked, non-gitignored path (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    logger.info(f"Starting page generation: db={args.db_url} output_dir={args.output_dir}")

    engine = create_engine(args.db_url)

    pesagens = pd.read_sql("SELECT * FROM pesagens ORDER BY id", engine)
    pesagens["parametros_qualidade"] = pesagens["parametros_qualidade"].apply(
        lambda v: json.loads(v) if isinstance(v, str) else (v or {})
    )
    fretes = pd.read_sql("SELECT * FROM fretes_colheita ORDER BY id", engine)
    logger.info(f"Read {len(pesagens)} pesagens rows, {len(fretes)} fretes_colheita rows")

    pesagens_dir = args.output_dir / "pesagens"
    fretes_dir = args.output_dir / "fretes"

    n_pesagens = 0
    skipped = []
    for row in pesagens.itertuples():
        try:
            filename, frontmatter, body = pesagem_page(row)
            write_page(pesagens_dir, filename, frontmatter, body)
            n_pesagens += 1
        except Exception as e:
            skipped.append(("pesagem", row.id, e))
            logger.warning(f"Skipped pesagem id={row.id} due to {e!r}")

    n_fretes = 0
    for row in fretes.itertuples():
        try:
            filename, frontmatter, body = frete_page(row)
            write_page(fretes_dir, filename, frontmatter, body)
            n_fretes += 1
        except Exception as e:
            skipped.append(("frete", row.id, e))
            logger.warning(f"Skipped frete id={row.id} due to {e!r}")

    logger.info(f"Wrote {n_pesagens} pesagem pages to {pesagens_dir}")
    logger.info(f"Wrote {n_fretes} frete pages to {fretes_dir}")
    logger.info(f"Total: {n_pesagens + n_fretes} pages in {args.output_dir}")
    if skipped:
        logger.warning(f"Skipped {len(skipped)} row(s) due to errors: {skipped}")


if __name__ == "__main__":
    main()
