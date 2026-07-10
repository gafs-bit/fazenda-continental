#!/usr/bin/env python3
"""Golden-answer regression harness for the Fazenda Continental Telegram bot.

Detects hallucination / drift over time by running a fixed set of known
questions through the SAME `ask_hermes` path the live bot uses, then checking
the answer against ground truth pulled from the authoritative database.

Checks performed per case:
  - EXACT  : answer must contain a literal substring (e.g. a romaneio/placa).
  - NUMBER : answer must contain a number within tolerance of the expected
             value (normalises thousands separators / decimal commas).
  - ABSENT : answer must state no record was found (for negative cases).

Exit code 0 = all pass, 1 = any failure (so a cron job / CI can alert).

Usage:
  python3 scripts/golden_check.py            # full run, prints report
  python3 scripts/golden_check.py --quiet    # only prints failures

Ground truth was extracted from `dbname=gbrain_dev` (read-only) and baked in
here so the harness is self-contained and needs no DB access at run time.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from telegram_bot.ask_hermes import ask_hermes  # noqa: E402


def _norm_num(s: str) -> float:
    """Parse a Brazilian-formatted number (1.234,56 -> 1234.56)."""
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s)


def _contains_number(text: str, expected: float, tol: float = 1.0) -> bool:
    for m in re.findall(r"\d[\d\.\,]*", text):
        try:
            if abs(_norm_num(m) - expected) <= tol:
                return True
        except ValueError:
            continue
    return False


# ── Ground truth (authored from dbname=gbrain_dev, read-only) ──────────────
# Cases exercise every tool path the bot uses.
CASES = [
    {
        "id": "romaneio-14683-record",
        "q": "Procure o romaneio 14683 e diga a placa e o motorista.",
        "kind": "exact",
        "expect": ["14683", "QAE2A51", "ANTONIO MARCOS ROMEIRA"],
    },
    {
        "id": "romaneio-14683-weight",
        "q": "Qual o peso liquido umido do romaneio 14683?",
        "kind": "number",
        "expect": 45960.0,
    },
    {
        "id": "total-peso-umido",
        "q": "Qual foi o total de peso liquido registrado nas pesagens?",
        "kind": "number",
        "expect": 8737460.0,
        "tol": 2000.0,
    },
    {
        "id": "max-peso-umido-record",
        "q": "Qual placa teve o maior peso liquido registrado nas pesagens?",
        "kind": "exact",
        "expect": ["QAE2A51"],
        "expect_number": 45960.0,
    },
    {
        "id": "distinct-placas",
        "q": "Quantas placas diferentes temos nas pesagens?",
        "kind": "number",
        "expect": 13,
    },
    {
        "id": "distinct-motoristas",
        "q": "Quantos motoristas diferentes aparecem nas pesagens?",
        "kind": "number",
        "expect": 19,
    },
    {
        "id": "nonexistent-romaneio",
        "q": "Qual a placa do romaneio 999999?",
        "kind": "absent",
    },
    # Cases below exercise the direct-tool tables added to replace gbrain
    # as the storage/retrieval layer (see docs/AUDIT.md, docs/PROJECT_LOG.md
    # for 2026-07-10) -- frete_get, uso_equipamentos_*, *_search_observacao.
    {
        "id": "frete-get-exact-lookup",
        "q": "Qual a área em hectares do talhão BL.023?",
        "kind": "number",
        "expect": 9.0,
        "tol": 0.1,
    },
    {
        "id": "uso-equipamentos-aggregate-hours",
        "q": "Quantas horas trabalhadas no total o equipamento 2085 registrou?",
        "kind": "number",
        "expect": 530.0,
        "tol": 1.0,
    },
    {
        "id": "uso-equipamentos-filter-funcionario",
        "q": "Quantas vezes o funcionário Jose Antonio Augusto Vaz usou o equipamento 2701?",
        "kind": "number",
        "expect": 384,
    },
    {
        "id": "uso-equipamentos-nonexistent-equipamento",
        "q": "Quais registros de uso existem para o equipamento 999999?",
        "kind": "absent",
    },
    {
        "id": "pesagem-search-observacao",
        "q": "Alguma pesagem tem observação mencionando 'ADVANTA 1151'?",
        "kind": "exact",
        "expect": ["ADVANTA"],
    },
]


async def run_case(case: dict) -> tuple[bool, str]:
    try:
        ans = await ask_hermes(case["q"])
    except Exception as e:
        return False, f"call error: {e!r}"

    kind = case["kind"]
    if kind == "exact":
        missing = [e for e in case["expect"] if e not in ans]
        if missing:
            return False, f"missing expected tokens {missing} | answer: {ans[:160]}"
        num = case.get("expect_number")
        if num is not None and not _contains_number(ans, num, case.get("tol", 1.0)):
            return False, f"expected number {num} not found in: {ans[:160]}"
        return True, "ok"
    if kind == "number":
        tol = case.get("tol", 1.0)
        if _contains_number(ans, case["expect"], tol):
            return True, "ok"
        return False, f"number {case['expect']} not found in: {ans[:160]}"
    if kind == "absent":
        if re.search(
            r"n(ão|ao)\s+encont|n(ão|ao)\s+exist|nenhum[a]?\s+.{0,20}?encontr|"
            r"nenhuma\s+correspond|no\s+record|inexistent|"
            r"n(ão|ao)\s+foi\s+encontrado|sem\s+registro",
            ans,
            re.I,
        ):
            return True, "ok"
        return False, f"expected 'not found' but got: {ans[:160]}"
    return False, f"unknown case kind {kind}"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    passed = 0
    failed = 0
    print("=== Golden-answer harness (Fazenda Continental) ===")
    for case in CASES:
        ok, detail = await run_case(case)
        if ok:
            passed += 1
            if not args.quiet:
                print(f"[PASS] {case['id']}")
        else:
            failed += 1
            print(f"[FAIL] {case['id']} — {detail}")

    print(f"\n=== {passed}/{passed+failed} passed ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
