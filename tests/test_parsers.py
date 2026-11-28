"""Testy parserów tekstu z wiki (fetch_data.py) na zapisanych stronach z tests/fixtures/.

    python3 -m unittest discover tests          # offline, na fixturach
    ARC_LIVE=1 python3 -m unittest discover tests  # do tego te same parsery na aktualnych stronach wiki

Fixtury to wikitext stron z 2026-11-28. Gdy wiki zmieni format, test „live” pokaże to od razu; po poprawie
parsera pobierz fixtury od nowa (python3 tests/refresh_fixtures.py) i uzupełnij oczekiwania.
"""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import fetch_data as f  # noqa: E402

FIX = HERE / "fixtures"
LIVE = os.environ.get("ARC_LIVE") == "1"


def fixture(name):
    return (FIX / name).read_text(encoding="utf-8")


class SmallHelpers(unittest.TestCase):
    def test_parse_ingredients(self):
        self.assertEqual(f.parse_ingredients("Chemicals:3, Plastic Parts:3"), [["Chemicals", 3], ["Plastic Parts", 3]])
        self.assertEqual(f.parse_ingredients("Anvil I:1:1"), [["Anvil I", 1]])  # resztki ":N" z ulepszeń broni
        self.assertEqual(f.parse_ingredients("Fabric"), [["Fabric", 1]])
        self.assertEqual(f.parse_ingredients(""), [])
        self.assertEqual(f.parse_ingredients(None), [])

    def test_norm_station(self):
        self.assertEqual(f.norm_station("Gunsmith III"), "Gunsmith 3")
        self.assertEqual(f.norm_station("Workbench"), "Workbench 1")
        self.assertEqual(f.norm_station(" Medical Lab 1 "), "Medical Lab 1")
        self.assertIsNone(f.norm_station("  "))

    def test_num(self):
        self.assertEqual(f.num("12"), 12)
        self.assertEqual(f.num("x", default=1), 1)
        self.assertEqual(f.num("0.5", float), 0.5)

    def test_clean_src(self):
        self.assertEqual(f.clean_src("Sold by [[Lance]] ({{Price|900}})"), "Sold by [[Lance]] (900 Coins)")
        self.assertEqual(f.clean_src("[[File:x.png|20px]] '''Bold'''<br>next"), "Bold, next")
        self.assertEqual(f.clean_src("Quests: {{Sourced from quests}}"), "Quests")


class Sources(unittest.TestCase):
    def test_flat_with_price(self):
        # Crafting i Quests są pomijane (mamy je z Cargo), cena z {{Price}} staje się tekstem.
        self.assertEqual(f.parse_sources(fixture("item_Adrenaline_Shot.wiki")),
                         [["Scavenging", []], ["Sold by [[Lance]] (900 Coins)", []]])

    def test_price_with_limit(self):
        self.assertEqual(f.parse_sources(fixture("item_Advanced_Camera.wiki")),
                         [["Sold by [[Shani]] (3,000 Coins, 3 per day)", []], ["Free [[Reward Pass]]", []]])

    def test_nesting(self):
        src = f.parse_sources(fixture("item_ARC_Circuitry.wiki"))
        self.assertEqual(len(src), 1)
        top, kids = src[0]
        self.assertEqual(top, "Scavenging")
        self.assertEqual(kids[0][0], "ARC")
        self.assertEqual([k[0] for k in kids[0][1]][:3], ["[[Baron Husk]]", "[[Bastion]]", "[[Courier]]"])
        self.assertEqual(len(kids[0][1]), 8)

    def test_no_section(self):
        self.assertEqual(f.parse_sources("Just text.\n== Trivia ==\n* nope"), [])

    def test_skipped_children_are_skipped(self):
        text = "== Sources ==\n* Crafting\n** [[Workbench]]\n* Scavenging\n== Next ==\n"
        self.assertEqual(f.parse_sources(text), [["Scavenging", []]])


class Amplified(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.amps, cls.levels = f.parse_amplified(fixture("Amplified_Weapons.wiki"))

    def test_counts(self):
        self.assertEqual(len(self.amps), 44)
        self.assertEqual(len(self.levels), 15)

    def test_first_entry(self):
        self.assertEqual(self.amps[0], {"weapon": "Kettle V", "amp": "X-Rounds", "item": "Fossilized Lightning",
                                        "qty": 3, "research": "Embedded Blast Engineering", "requires": None})
        self.assertEqual(self.levels[:2], [["Kettle V", "Kettle IV"], ["Rattler V", "Rattler IV"]])

    def test_shape(self):
        for a in self.amps:
            self.assertRegex(a["weapon"], r" V$")
            self.assertTrue(a["amp"] and a["item"])
            self.assertIsInstance(a["qty"], int)
            self.assertGreater(a["qty"], 0)


class AmpResearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = f.parse_amp_research(fixture("Amplified_Research.wiki"))

    def test_count(self):
        self.assertEqual(len(self.rows), 28)

    def test_first_project(self):
        first = [r for r in self.rows if r["project"] == "Action Economy"]
        self.assertEqual({(r["item"], r["qty"]) for r in first}, {("Sentinel Firing Core", 8), ("Research Points", 5000)})
        for r in first:
            self.assertEqual(r["unlocks"], "Ergonomic Bolt")
            self.assertEqual(r["task"], ["(In one round)", "Deal 1,000 damage with a [[Hairpin]]"])

    def test_every_project_has_unlock_and_points(self):
        projects = {r["project"] for r in self.rows}
        for p in projects:
            rows = [r for r in self.rows if r["project"] == p]
            self.assertTrue(all(r["unlocks"] for r in rows), p)
            self.assertIn("Research Points", [r["item"] for r in rows], p)


@unittest.skipUnless(LIVE, "ustaw ARC_LIVE=1, żeby sprawdzić aktualne strony wiki")
class LiveWiki(unittest.TestCase):
    """Te same parsery na stronach pobranych teraz: pusty albo niepełny wynik znaczy, że wiki zmieniła format."""

    def test_amplified_weapons(self):
        amps, levels = f.parse_amplified(f.wikitext("Amplified Weapons"))
        self.assertGreaterEqual(len(amps), 30)
        self.assertGreaterEqual(len(levels), 10)
        self.assertGreater(sum(1 for a in amps if a["research"]), len(amps) // 2)

    def test_amplified_research(self):
        rows = f.parse_amp_research(f.wikitext("Amplified Research"))
        self.assertGreaterEqual(len(rows), 20)
        self.assertTrue(any(r["item"] == "Research Points" for r in rows))
        self.assertTrue(all(r["unlocks"] for r in rows))

    def test_item_sources(self):
        pages = f.pages_wikitext(["Adrenaline Shot", "ARC Circuitry"])
        self.assertIn(["Scavenging", []], f.parse_sources(pages["Adrenaline Shot"]))
        circ = f.parse_sources(pages["ARC Circuitry"])
        self.assertTrue(circ and circ[0][1], circ)


if __name__ == "__main__":
    unittest.main()
