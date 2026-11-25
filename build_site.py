#!/usr/bin/env python3
"""Kopiuje stronę do aplikacji homelaba (arc.billy.pl), jako samodzielny dokument HTML.

Użycie:  python3 build_site.py [katalog_aplikacji]
         (domyślnie: ~/dev/private-homelab/services/games/arc-atlas)

index.html jest pisany pod artefakty Claude, które same dokładają szkielet (doctype, charset, viewport,
mały reset). Tutaj dokładamy go sami. fetch_data.py trafia do app/, skąd kontener odświeża data.json.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT = Path.home() / "dev/private-homelab/services/games/arc-atlas"

HEAD = """<!doctype html>
<!-- Wygenerowane przez build_site.py z projektu arc-crafting: nie edytuj tutaj. -->
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
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
    out = HEAD + head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "") + \
        "\n</head>\n<body>" + body + "\n</body>\n</html>\n"
    (app / "web").mkdir(parents=True, exist_ok=True)
    (app / "app").mkdir(parents=True, exist_ok=True)
    (app / "web/index.html").write_text(out, encoding="utf-8")
    shutil.copy2(HERE / "fetch_data.py", app / "app/fetch_data.py")
    print(f"Zapisano {app / 'web/index.html'} i {app / 'app/fetch_data.py'}")


if __name__ == "__main__":
    main()
