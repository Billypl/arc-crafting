# ARC Crafting Atlas

Przeglądarka zależności craftingu i recyklingu w ARC Raiders, zbudowana na danych z https://arcraiders.wiki/ (Cargo API).

- `fetch_data.py` pobiera dane z wiki i zapisuje je do `data.json`: tabele Cargo oraz amplifikacje broni, które wiki ma tylko w tekście stron Amplified Weapons i Amplified Research (gdy ich parsowanie nic nie znajdzie, zostają poprzednie dane). Źródła łupu (sekcja „Sources”) i punkty badań bierze ze stron przedmiotów, pobieranych hurtem po 50 na zapytanie (ok. 12 zapytań); nagrody z questów i projektów są w Cargo. Uruchom go ponownie po aktualizacji wiki: `python3 fetch_data.py`
- `index.html` to strona, która czyta `data.json`.

Uruchomienie lokalne (przeglądarka nie wczyta `data.json` z `file://`):

```sh
python3 -m http.server 8000
# otwórz http://localhost:8000
```

## arc.billy.pl

Strona jest hostowana na Pi jako aplikacja homelaba `services/games/arc-atlas` (szczegóły w jej README).
Po zmianie `index.html` albo `fetch_data.py`: `python3 build_site.py` zapisuje samodzielną wersję strony
i skrypt do repo homelaba. Potem commit tam i `git pull` na Pi. Dane na Pi odświeżają się same raz w tygodniu.
