# Hogebrug status checker

Deze repository bevat een klein Python-hulpprogramma dat de actuele status van
**de Hogebrug in Overschie** probeert te bepalen via het open-data portaal van
Rotterdam. De logica is defensief opgebouwd zodat kleine wijzigingen in de
brondata opgevangen kunnen worden.

## Installatie

Het project gebruikt een moderne Python toolchain (Python 3.10 of hoger).
Installeer eerst de afhankelijkheden:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Gebruik

Voer de CLI uit met:

```bash
python -m hogebrug_status
```

Standaard worden de vijf meest recente records van het dataset `brugopeningen`
ogevraagd. De CLI toont een compacte tekstuele status, inclusief de meest
recente observatietijd en de bron-URL.

Belangrijke opties:

- `--bridge`: voer een andere brugnaam in (standaard: `Hogebrug`).
- `--dataset`: wijzig het dataset-id wanneer Rotterdam het dataportaal aanpast
  (standaard: `brugopeningen`).
- `--rows`: hoeveel records moeten worden opgehaald om een status te bepalen
  (standaard: 5).
- `--url`: override voor het API-endpoint wanneer het portaal verandert.
- `--json`: toon de ruwe interpretatie als JSON in plaats van tekst.

Voorbeeld uitvoer:

```
De Hogebrug is open. (Veld 'melding' meldt: Brug weer open voor verkeer)
Laatste melding: 2024-04-20T11:00:00+02:00
Bron: https://opendata.rotterdam.nl/api/records/1.0/search/
```

## Testen

Tests draaien met `pytest`:

```bash
pytest
```

De tests dekken zowel de interpretatielogica als de CLI.

## Hoe het werkt

1. De `BridgeStatusChecker` haalt records op uit het open-data portaal waarbij
   gezocht wordt op de opgegeven brugnaam.
2. Voor elk record probeert de checker meerdere strategieën:
   - Tekstvelden met woorden zoals "open" of "dicht" worden herkend.
   - Datum- en tijdvelden met woorden als `opening` of `sluiting` worden
     vergeleken om te bepalen of een sluiting bekend is.
   - Booleaanse of 0/1 velden worden geïnterpreteerd als directe status.
3. Het meest recente record met een herleidbare status wordt teruggegeven.

Als geen enkele strategie slaagt, meldt de CLI dat de status niet bepaald kon
worden. Pas in dat geval de dataset-instellingen aan of controleer handmatig de
open-data bron.
