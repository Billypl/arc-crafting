#!/usr/bin/env python3
"""Pobiera od nowa strony wiki, na których działają testy parserów (tests/fixtures/*.wiki).

Po pobraniu uruchom testy: zmienione liczby albo wpisy pokażą, co wiki zmieniła; popraw parser
albo oczekiwania w test_parsers.py.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import fetch_data as f  # noqa: E402

PAGES = ["Amplified Weapons", "Amplified Research"]
ITEMS = ["ARC Alloy", "ARC Circuitry", "ARC Conductive Coupler", "Adrenaline Shot", "Advanced Camera"]

for p in PAGES:
    (HERE / "fixtures" / f"{p.replace(' ', '_')}.wiki").write_text(f.wikitext(p), encoding="utf-8")
for n, t in f.pages_wikitext(ITEMS).items():
    (HERE / "fixtures" / f"item_{n.replace(' ', '_')}.wiki").write_text(t, encoding="utf-8")
print("Zapisano", len(PAGES) + len(ITEMS), "stron w", HERE / "fixtures")
