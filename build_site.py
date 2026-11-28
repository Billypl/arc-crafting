#!/usr/bin/env python3
"""Kopiuje stronę do aplikacji homelaba (arc.billy.pl), jako samodzielny dokument HTML.

Użycie:  python3 build_site.py [katalog_aplikacji]
         (domyślnie: ~/dev/private-homelab/services/games/arc-atlas)

index.html jest pisany pod artefakty Claude, które same dokładają szkielet (doctype, charset, viewport,
mały reset). Tutaj dokładamy go sami. fetch_data.py trafia do app/, skąd kontener odświeża data.json.
"""
import html
import shutil
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
URL = "https://arc.billy.pl/"
DESC = ("Crafting i recykling w ARC Raiders: do czego przyda się przedmiot, jak go zdobyć, graf zależności "
        "i kalkulator surowców. Dane z ARC Raiders Wiki.")
# Ikona: trzy połączone węzły (graf) w bursztynie motywu na śliwkowej czerni.
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#130918"/>'
        '<path d="M9 22 16 10 23 22Z" fill="none" stroke="#f1aa1c" stroke-width="2.5" stroke-linejoin="round"/>'
        '<circle cx="16" cy="10" r="4" fill="#f1aa1c"/><circle cx="9" cy="22" r="4" fill="#f1aa1c"/>'
        '<circle cx="23" cy="22" r="4" fill="#f1aa1c"/></svg>')
DEFAULT = Path.home() / "dev/private-homelab/services/games/arc-atlas"

HEAD = """<!doctype html>
<!-- Wygenerowane przez build_site.py z projektu arc-crafting: nie edytuj tutaj. -->
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="DESC">
<meta name="theme-color" content="#130918">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ARC Crafting Atlas">
<meta property="og:title" content="ARC Raiders Crafting Atlas">
<meta property="og:description" content="DESC">
<meta property="og:url" content="URL">
<meta property="og:locale" content="pl_PL">
<meta name="twitter:card" content="summary">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,ICON">
<style>
:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px) }
body { margin: 0; font: 14px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif }
img { max-width: 100% }
[hidden] { display: none !important }
</style>
"""


def main():
    app = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    page = (HERE / "index.html").read_text(encoding="utf-8")
    # Tytuł, czcionki i style strony idą do <head>; reszta (od pierwszego elementu treści) do <body>.
    cut = page.index("</style>") + len("</style>")
    head, body = page[:cut], page[cut:]
    head_tags = HEAD.replace("DESC", html.escape(DESC)).replace("URL", URL) \
        .replace("ICON", urllib.parse.quote(ICON))
    out = head_tags + head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "") + \
        "\n</head>\n<body>" + body + "\n</body>\n</html>\n"
    (app / "web").mkdir(parents=True, exist_ok=True)
    (app / "app").mkdir(parents=True, exist_ok=True)
    (app / "web/index.html").write_text(out, encoding="utf-8")
    shutil.copy2(HERE / "fetch_data.py", app / "app/fetch_data.py")
    print(f"Zapisano {app / 'web/index.html'} i {app / 'app/fetch_data.py'}")


if __name__ == "__main__":
    main()
