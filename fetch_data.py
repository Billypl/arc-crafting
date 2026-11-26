#!/usr/bin/env python3
"""Pobiera dane craftingu i recyklingu z ARC Raiders Wiki (Cargo API) do data.json.

Użycie:  python3 fetch_data.py [ścieżka_wyjściowa]   (domyślnie: data.json obok skryptu)
Uruchom ponownie po aktualizacji wiki, żeby odświeżyć dane.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://arcraiders.wiki/w/api.php"
UA = "arc-crafting-graph/1.0 (personal crafting helper)"
PAGE = 500


def cargo(table, fields, where=None):
    """Zwraca wszystkie wiersze tabeli Cargo (z paginacją)."""
    rows, offset = [], 0
    while True:
        params = {
            "action": "cargoquery", "format": "json", "tables": table,
            "fields": fields, "limit": PAGE, "offset": offset,
        }
        if where:
            params["where"] = where
        url = API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        if "error" in data:
            raise RuntimeError(f"{table}: {data['error']}")
        batch = [{k: html.unescape(v) if isinstance(v, str) else v
                  for k, v in row["title"].items()} for row in data["cargoquery"]]
        rows += batch
        if len(batch) < PAGE:
            return rows
        offset += PAGE
        time.sleep(0.5)


def category_members(cat):
    """Tytuły stron (przestrzeń główna) w kategorii wiki."""
    out, cont = [], {}
    while True:
        params = {"action": "query", "format": "json", "list": "categorymembers",
                  "cmtitle": cat, "cmnamespace": 0, "cmlimit": 500, **cont}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        out += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
        if "continue" not in data:
            return out
        cont = data["continue"]


def wikitext(page):
    """Surowy wikitext strony."""
    params = {"action": "parse", "format": "json", "page": page, "prop": "wikitext"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["parse"]["wikitext"]["*"]


def pages_wikitext(titles):
    """Wikitext wielu stron naraz, po 50 na zapytanie (limit API), zamiast jednego zapytania na stronę.
    Przekierowania są rozwijane, a wynik jest pod tytułem, o który pytaliśmy."""
    out, titles = {}, list(titles)
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        params = {"action": "query", "format": "json", "formatversion": 2, "prop": "revisions",
                  "rvprop": "content", "rvslots": "main", "redirects": 1, "titles": "|".join(chunk)}
        req = urllib.request.Request(API, data=urllib.parse.urlencode(params).encode(), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            q = json.load(r)["query"]
        back = {t: t for t in chunk}
        for k in ("normalized", "redirects"):
            for m in q.get(k, []):
                back[m["to"]] = back.get(m["from"], m["from"])
        for pg in q.get("pages", []):
            if pg.get("revisions"):
                out[back.get(pg["title"], pg["title"])] = pg["revisions"][0]["slots"]["main"]["content"]
        time.sleep(0.5)
    return out


# Pozycje sekcji „Sources”, które strona dokłada sama z innych danych: crafting i recykling mamy z Cargo,
# nagrody z questów i projektów też (questItems/projectItems z context=reward).
# Sam link do Research Station przy blueprintach to przepis badawczy, który też jest w Cargo.
SRC_SKIP = re.compile(r"^(crafting|recycling|salvaging|recycling or salvaging.*|quests?:?|projects?:?"
                      r"|\[\[Workshop[^\]]*\]\])$", re.I)


def clean_src(t):
    """Jedna pozycja listy źródeł jako zwykły tekst; linki zostają jako [[Cel]] / [[Cel|etykieta]]."""
    t = re.sub(r"\{\{Price\|([\d,]+)(?:\|([^|}=]+)(?=[|}]))?[^}]*\}\}",
               lambda m: f"{m.group(1)} {(m.group(2) or 'Coins').strip()}", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"<br\s*/?>", ", ", t)
    t = re.sub(r"<[^>]+>", "", t).replace(B3, "").replace("''", "")
    t = re.sub(r"\[\[(?:File|Plik):[^\]]*\]\]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" :,")
    return html.unescape(t)


def parse_sources(text):
    """Sekcja == Sources == jako drzewo [[tekst, [dzieci]], …] (zagnieżdżenie z liczby gwiazdek)."""
    m = re.search(r"^==\s*Sources?\s*==\s*$(.*?)(?=^==[^=])", text + "\n==", re.S | re.M)
    if not m:
        return []
    root = []
    stack = [(0, root)]
    for line in m.group(1).splitlines():
        lm = re.match(r"^(\*+)\s*(.*)$", line.strip())
        if not lm:
            continue
        depth, t = len(lm.group(1)), clean_src(lm.group(2))
        while stack[-1][0] >= depth:
            stack.pop()
        if not t or (depth == 1 and SRC_SKIP.match(t)):
            stack.append((depth, []))  # dzieci pominiętej pozycji też pomijamy
            continue
        node = [t, []]
        stack[-1][1].append(node)
        stack.append((depth, node[1]))
    return root


LINKED = re.compile(r"([\d,]+)\s*\[\[([^\]|#]+)(?:[^\]]*)\]\]")
TIER = {"Common": "I", "Uncommon": "II", "Rare": "III", "Epic": "IV", "Legendary": "V"}
B3 = "'" * 3  # pogrubienie w wikitekście


def parse_amplified(text):
    """Strona „Amplified Weapons”: dla każdej broni na poziomie V jej amplifikacje i ich materiały.

    Tych danych nie ma w Cargo, tylko w tekście strony: blok broni zaczyna się od {{ILink|…|2=Kettle V|…|4=Kettle_IV}},
    a każda amplifikacja to tabelka z nagłówkiem „! … | Nazwa” i pogrubionymi liniami Materials, Research, Requires.
    Zwraca (amplifikacje, ulepszenia do V jako [broń V, broń bazowa])."""
    amps, levels = [], []
    for b in re.split(r"\{\{ILink\|", text)[1:]:
        head = b.split("}}", 1)[0]
        args = dict(a.split("=", 1) for a in head.split("|") if "=" in a)
        weapon, base = args.get("2", "").strip(), args.get("4", "").replace("_", " ").strip()
        if not weapon:
            continue
        if base:
            levels.append([weapon, base])
        for t in re.split(r"\n\{\|", b)[1:]:
            t = t.split("\n|}", 1)[0]
            m = re.search(r"^!.*\|\s*([^|\n]+?)\s*$", t, re.M)
            mat = re.search(B3 + r"Materials:" + B3 + r"(.*)", t)
            if not (m and mat):
                continue
            res = re.search(B3 + r"Research:" + B3 + r"\s*\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", t)
            req = re.search(B3 + r"Requires:" + B3 + r"\s*([^<\n]+)", t)
            for qty, item in LINKED.findall(mat.group(1)):
                amps.append({"weapon": weapon, "amp": m.group(1), "item": item.strip(), "qty": num(qty.replace(",", ""), default=1),
                             "research": res.group(1).strip() if res else None,
                             "requires": req.group(1).strip() if req else None})
    return amps, levels


def parse_amp_research(text):
    """Strona „Amplified Research”: koszt każdego projektu badawczego (krok 2) i amplifikacja, którą odblokowuje."""
    out = []
    for part in re.split(r"^=== " + B3, text, flags=re.M)[1:]:
        name = part.split(B3, 1)[0].strip()
        un = re.search(r"^\|\s*(?!valign)([^|\n][^\n]*)$", part, re.M)
        step2 = part.split("Step 2 =", 1)[1].split("</tabber>", 1)[0] if "Step 2 =" in part else ""
        items = LINKED.findall(step2)
        rp = re.search(r"\*\s*([\d,]+)\s+Research Points", step2)
        if rp:
            items.append((rp.group(1), "Research Points"))
        for qty, item in items:
            out.append({"project": name, "unlocks": un.group(1).strip() if un else None,
                        "item": item.strip(), "qty": num(qty.replace(",", ""), default=1)})
    return out


def num(v, cast=int, default=None):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"}


def norm_station(s):
    s = s.strip()
    if not s:
        return None
    m = re.match(r"^(.*?)\s+([IV]+)$", s)
    if m and m.group(2) in ROMAN:
        s = f"{m.group(1)} {ROMAN[m.group(2)]}"
    if s == "Workbench":
        s = "Workbench 1"
    return s


def parse_ingredients(s):
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, qty = part.rpartition(":")
        if not name:
            name, qty = qty, "1"
        # Ulepszenia broni mają wpisy typu "Anvil I:1:1" – odcinamy resztki ":N" z nazwy.
        name = re.sub(r"(:\d+)+$", "", name.strip())
        out.append([name, num(qty, default=1)])
    return out


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data.json")

    print("items…")
    items = {}
    for r in cargo("items", "name,rarity,type,sellprice,weight,stacksize,raritysort,location"):
        if not r.get("name"):
            continue
        items[r["name"]] = {
            "rarity": r.get("rarity") or None,
            "type": r.get("type") or None,
            "value": num(r.get("sellprice")),
            "weight": num(r.get("weight"), float),
            "stack": num(r.get("stacksize")),
        }
        loc = [x.strip() for x in re.split(r",|<br\s*/?>", r.get("location") or "") if x.strip()]
        if loc:
            items[r["name"]]["loc"] = loc

    print("crafting…")
    merged = {}
    for r in cargo("crafting", "resultItem,resultQty,ingredients,requireBlueprint,requireStation,requireSkill"):
        res = r.get("resultItem")
        if not res:
            continue
        ins = parse_ingredients(r.get("ingredients"))
        if not ins:
            continue
        qty = num(r.get("resultQty"), default=1) or 1
        stations = [s for s in (norm_station(x) for x in (r.get("requireStation") or "").split(",")) if s]
        key = (res, qty, json.dumps(sorted(ins)))
        rec = merged.setdefault(key, {"out": res, "qty": qty, "in": ins, "stations": [],
                                      "blueprint": r.get("requireBlueprint") or None,
                                      "skill": r.get("requireSkill") or None})
        for s in stations:
            if s not in rec["stations"]:
                rec["stations"].append(s)
    recipes = list(merged.values())

    print("recycling…")
    recycle = {}
    for r in cargo("recycling", "recipeType,inputItem,outputItem,outputQty"):
        if not (r.get("inputItem") and r.get("outputItem")):
            continue
        k = (r.get("recipeType") or "recycling", r["inputItem"])
        recycle.setdefault(k, []).append([r["outputItem"], num(r.get("outputQty"), default=1)])
    recycle = [{"type": t, "in": i, "out": o} for (t, i), o in sorted(recycle.items())]

    print("workshop upgrades…")
    upgrades = [{"station": r.get("station"), "level": num(r.get("stationLevel")),
                 "item": r.get("itemName"), "qty": num(r.get("qty"), default=1)}
                for r in cargo("workshopUpgrades", "station,stationLevel,itemName,qty") if r.get("itemName")]

    print("projects…")
    projects = [{"project": r.get("projectName"), "stage": num(r.get("stage")),
                 "item": r.get("itemName"), "qty": num(r.get("qty"), default=1)}
                for r in cargo("projectItems", "projectName,stage,context,itemName,qty", where="context='require'")
                if r.get("itemName")]

    print("quests…")
    quests = [{"quest": r.get("quest"), "item": r.get("itemName"), "qty": num(r.get("qty"), default=1)}
              for r in cargo("questItems", "_pageName=quest,context,itemName,qty", where="context='require'")
              if r.get("itemName")]

    print("rewards…")
    rewards = [{"quest": r.get("quest"), "item": r.get("itemName"), "qty": num(r.get("qty"), default=1),
                **({"grant": True} if r.get("context") == "grant" else {})}
               for r in cargo("questItems", "_pageName=quest,context,itemName,qty",
                              where="context='reward' OR context='grant'") if r.get("itemName")]
    rewards += [{"project": r.get("projectName"), "stage": num(r.get("stage")), "item": r.get("itemName"),
                 "qty": num(r.get("qty"), default=1)}
                for r in cargo("projectItems", "projectName,stage,context,itemName,qty", where="context='reward'")
                if r.get("itemName")]

    # Wpisy z podstron (np. "Użytkownik/Tabela") to brudnopisy, nie prawdziwe przedmioty.
    junk = lambda n: "/" in (n or "")
    recipes = [r for r in recipes if not junk(r["out"]) and not any(junk(n) for n, _ in r["in"])]
    recycle = [r for r in recycle if not junk(r["in"])]

    # Bronie nie mają wpisów w tabeli items: rozpoznajemy je po kategorii wiki (z rzadkością).
    print("weapons…")
    weapon_rarity = {w: None for w in category_members("Category:Weapons")}
    for rar in ("Common", "Uncommon", "Rare", "Epic", "Legendary", "Amplified"):
        for w in category_members(f"Category:{rar} Weapons"):
            weapon_rarity[w] = rar

    # Strony przedmiotów: skąd wypadają (sekcja „Sources”) i, dla przedmiotów badawczych, ile dają punktów badań
    # ({{Price|1000|Research Points}} albo zwykły tekst „grants 150 Research Points”). Wszystkie strony idą
    # hurtem, ~12 zapytań. Gdy pobranie się nie uda, zostają poprzednie dane z data.json.
    print("item pages…")
    prev = {}
    try:
        # Kontener na Pi pisze do data.json.tmp i podmienia plik dopiero po udanym pobraniu,
        # więc poprzednie dane leżą pod nazwą bez „.tmp”.
        prev_path = out_path.with_suffix("") if out_path.suffix == ".tmp" else out_path
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        pages = pages_wikitext(items)
    except Exception as e:  # noqa: BLE001 – źródła to dodatek, nie mogą zatrzymać pobierania
        print(f"UWAGA: strony przedmiotów: {e}; zostawiam poprzednie źródła i punkty badań.")
        pages = None
    for n, it in items.items():
        if pages is None:
            old = prev.get("items", {}).get(n, {})
            it.update({k: old[k] for k in ("src", "rp") if k in old})
            continue
        text = pages.get(n, "")
        src = parse_sources(text)
        if src:
            it["src"] = src
        if it["type"] == "Research Item":
            m = re.search(r"\{\{Price\|([\d,]+)\|Research Points|grants\s+([\d,]+)\s+\[*Research Points", text)
            if m:
                it["rp"] = num((m.group(1) or m.group(2)).replace(",", ""))

    # Amplifikacje (broń na poziomie V) są tylko w tekście dwóch stron wiki, nie w Cargo. Gdy parser nic nie
    # znajdzie (ktoś przebudował stronę), bierzemy poprzednie dane z data.json i ostrzegamy, zamiast je zgubić.
    print("amplifications…")
    amps, levels = parse_amplified(wikitext("Amplified Weapons"))
    research = parse_amp_research(wikitext("Amplified Research"))
    if not amps:
        amps = prev.get("amps", [])
        levels = [[r["out"], r["in"][0][0]] for r in prev.get("recipes", []) if r.get("amplified")]
        print(f"UWAGA: nie znalazłem amplifikacji na stronie Amplified Weapons, zostawiam poprzednie ({len(amps)}).")
    if not research:
        research = prev.get("research", [])
        print(f"UWAGA: nie znalazłem badań na stronie Amplified Research, zostawiam poprzednie ({len(research)}).")
    # Ulepszenie do V: broń z poprzedniego poziomu + moduł amplifikacji zależny od rzadkości broni (tabela
    # „Upgrading” na tej samej stronie). Dokładamy je jako zwykłe przepisy: graf i kalkulator liczą je jak inne ulepszenia.
    have = {r["out"] for r in recipes}
    for weapon, base in levels:
        tier = TIER.get(weapon_rarity.get(re.sub(r"\s+(I|II|III|IV|V)$", "", base)) or "")
        if weapon in have or not tier:
            continue
        recipes.append({"out": weapon, "qty": 1, "in": [[base, 1], [f"Amplification Module Mk. {tier}", 1]],
                        "stations": ["Gunsmith 4"], "blueprint": None, "skill": None, "amplified": True})
    used = ({r["out"] for r in recipes} | {n for r in recipes for n, _ in r["in"]} |
            {r["in"] for r in recycle} | {o for r in recycle for o, _ in r["out"]})
    for n in used - set(items):
        base = re.sub(r"\s+(I|II|III|IV|V)$", "", n)
        if base in weapon_rarity:
            items[n] = {"rarity": weapon_rarity[base], "type": "Weapon", "value": None, "weight": None, "stack": None}

    data = {
        "source": "https://arcraiders.wiki/",
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "items": items, "recipes": recipes, "recycle": recycle,
        "upgrades": upgrades, "projects": projects, "quests": quests,
        "amps": amps, "research": research, "rewards": rewards,
    }

    # Jeden rekord na linię: plik da się czytać i porównywać w diffie.
    lines = ["{"]
    keys = list(data)
    for i, k in enumerate(keys):
        v = data[k]
        comma = "," if i < len(keys) - 1 else ""
        if isinstance(v, list):
            body = ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in v)
            lines.append(f'"{k}": [\n{body}\n]{comma}')
        elif isinstance(v, dict):
            body = ",\n".join(f"  {json.dumps(n, ensure_ascii=False)}: {json.dumps(x, ensure_ascii=False)}"
                              for n, x in sorted(v.items()))
            lines.append(f'"{k}": {{\n{body}\n}}{comma}')
        else:
            lines.append(f'"{k}": {json.dumps(v, ensure_ascii=False)}{comma}')
    lines.append("}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Zapisano {out_path}: {len(items)} przedmiotów, {len(recipes)} przepisów, "
          f"{len(recycle)} rozbiórek, {len(upgrades)} ulepszeń, {len(projects)} projektów, {len(quests)} questów, "
          f"{len(amps)} materiałów amplifikacji, {len(research)} kosztów badań, {len(rewards)} nagród, "
          f"{sum(1 for it in items.values() if it.get('src'))} przedmiotów ze źródłami")


if __name__ == "__main__":
    main()
