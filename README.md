# Statische Karten als PNG

Dieses Verzeichnis erstellt sieben Karten aus der mitgelieferten Excel-Datei. Jede Karte wird als PNG gespeichert. Die Karten zeigen dieselben Themen wie die interaktive Karte. Das Verzeichnis kann auch einzeln in ein anderes Projekt kopiert werden.

## Starten

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python make_maps.py
```

Die fertigen Bilder liegen als `output/karte1.png` bis `output/karte7.png` vor:

| Datei | Inhalt |
| --- | --- |
| `karte1.png` | Kreise |
| `karte2.png` | Schulämter |
| `karte3.png` | Alle allgemeinbildenden Schulen |
| `karte4.png` | Schulen der unteren Schulaufsicht |
| `karte5.png` | Schulen der oberen Schulaufsicht |
| `karte6.png` | Schulträger und externe Verwaltungen |
| `karte7.png` | Schulträgergebiete |

## Daten ändern

- `data/workbook.xlsx` enthält die Schulen, Schulämter und Schulträger. Die erste Zeile enthält die Spaltennamen. Für Schulämter und Träger zählt jeweils die erste passende Datenzeile.
- `data/overrides.json` enthält einzelne korrigierte Adressen oder Koordinaten. Alte Träger-Einträge verwenden `carrier`. Einträge für Schulen, Schulämter oder Verwaltungen verwenden `type` und `name`. Koordinaten stehen als `[Längengrad, Breitengrad]`. Die englischen Feldnamen in dieser Datei gehören zum vorhandenen Datenformat und bleiben deshalb bestehen.
- `cache/coordinates.json` enthält bereits gefundene Adressen und Koordinaten. Bei erneutem Start werden diese genutzt. Ein Eintrag mit `null` bedeutet, dass für die Adresse kein Standort gefunden wurde.
- `output/missing_addresses.csv` listet fehlende Standorte mit Typ, Name, Adresse und Fehlerursache. Betroffene Orte erscheinen nicht auf der Karte. Adressen lassen sich in der Excel-Datei oder über `data/overrides.json` korrigieren.

Neue Adressen sucht das Programm mit geopy über den Dienst Nominatim von OpenStreetMap. Dafür ist Internet nötig. Der hellgraue Kartenhintergrund kommt von Esri. contextily speichert heruntergeladene Bildteile in `cache/contextily/`. Der bisherige Cache in `cache/tiles/` wird nicht übernommen. Für den ersten Lauf mit dem neuen Hintergrund-Cache ist Internet nötig. Ohne Verbindung und ohne passende gespeicherte Bildteile bleibt der Hintergrund einfarbig.

`map_data.py` liest die Excel-Daten mit pandas und sucht Standorte mit geopy. `make_maps.py` verarbeitet Kreisgrenzen mit GeoPandas, lädt den Hintergrund mit contextily und speichert die Karten. Die Dateinamen bleiben erhalten, damit der Startbefehl und vorhandene Daten weiter funktionieren.

Bei Karte 6 zeigt ein Quadrat den Schulträger. Ein kleines rosa Dreieck zeigt eine Verwaltung am selben Standort und steht mit Abstand über dem Quadrat. Orange Dreiecke zeigen reine externe Verwaltungen. Die rosa Linien verbinden Träger und Verwaltung. Ein Pfeilkopf zeigt bei einer Verwaltung mit Trägereigenschaft zum Träger. Bei einer reinen externen Verwaltung zeigt die Linie vom Träger zur Verwaltung und hat keinen Pfeilkopf. Karte 7 bildet pro Träger eine umhüllende Fläche um dessen Schulen und, falls bekannt, seinen Sitz. Sie zeigt damit eine grafische Zuordnung, keine amtliche Gebietsgrenze.
