"""Liest Schul- und Trägerdaten und bestimmt ihre Standorte für sieben Karten."""

import csv
import json
from pathlib import Path

from geopy.exc import GeopyError
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
import pandas as pd

# Konstanten
ORDNER = Path(__file__).resolve().parent
DATEN = ORDNER / "data"
KOORDINATEN_CACHE = ORDNER / "cache" / "coordinates.json"
FEHLENDE_ADRESSEN = ORDNER / "output" / "missing_addresses.csv"
NOMINATIM_USER_AGENT = "reform-static-school-maps/1.0"


def excel_zeilen_lesen():
    """Liest das erste Tabellenblatt. Die Überschriften werden Feldnamen."""
    tabelle = pd.read_excel(DATEN / "workbook.xlsx", dtype=object,
                            keep_default_na=False)
    return tabelle.replace("", None).to_dict("records")


def adresse(zeile, rolle):
    """Setzt die Adresse wie beim interaktiven Excel-Import zusammen."""
    # "rolle" wählt die Excel-Spalten für Schule, Schulamt oder Träger aus.
    # Die Kürzel stammen aus der gelieferten Tabelle.
    strasse = zeile.get("sh_%s_str_nr" % rolle)
    postleitzahl = zeile.get("sh_%s_plz" % rolle)
    ort = zeile.get("sh_%s_ort" % rolle)
    if strasse is None or postleitzahl is None or ort is None:
        return None
    # Excel liest Postleitzahlen teils als Zahl mit ".0" ein.
    return "%s, %s %s" % (strasse, str(postleitzahl).split(".")[0], ort)


def _gueltiger_punkt(punkt):
    """Prüft ein Paar aus Längengrad und Breitengrad."""
    return (isinstance(punkt, list) and len(punkt) == 2
            and all(isinstance(wert, (int, float)) for wert in punkt))


class Standortsuche:
    """Sucht Adressen einmalig und merkt sich gefundene Koordinaten."""

    def __init__(self):
        self.cache = (json.loads(KOORDINATEN_CACHE.read_text(encoding="utf-8"))
                      if KOORDINATEN_CACHE.exists() else {})
        geocoder = Nominatim(user_agent=NOMINATIM_USER_AGENT, timeout=20)
        self.geocode = RateLimiter(geocoder.geocode, min_delay_seconds=1.2,
                                  max_retries=0, swallow_exceptions=False)
        self.fehlende = set()
        self.geaendert = False
        self.versucht = set()

    def _als_fehlend_melden(self, rolle, name, adress_text, fehler):
        """Merkt einen fehlenden Standort samt Ursache für den CSV-Bericht."""
        self.fehlende.add((rolle, str(name), adress_text or "", fehler))

    def finden(self, adress_text, rolle, name, vorgegebener_punkt=None):
        """Nutzt Vorgabe, Cache oder Nominatim. Ohne Standort folgt None."""
        # Manuell geprüfte Koordinaten haben Vorrang vor allen Suchergebnissen.
        if _gueltiger_punkt(vorgegebener_punkt):
            return vorgegebener_punkt
        if not adress_text:
            self._als_fehlend_melden(
                rolle, name, adress_text, "Adresse unvollständig"
            )
            return None
        if _gueltiger_punkt(self.cache.get(adress_text)):
            return self.cache[adress_text]
        # Ein Cache-Eintrag mit null heißt: Die Adresse wurde ohne Treffer gesucht.
        # Auch innerhalb eines Laufs wird dieselbe Adresse nicht erneut angefragt.
        if adress_text in self.cache or adress_text in self.versucht:
            self._als_fehlend_melden(
                rolle, name, adress_text, "Kein Nominatim-Treffer (Cache)"
            )
            return None
        self.versucht.add(adress_text)

        try:
            treffer = self.geocode(adress_text)
            if treffer:
                punkt = [treffer.longitude, treffer.latitude]
                self.cache[adress_text] = punkt
                self.geaendert = True
                return punkt
        except GeopyError as fehler:
            print("Adresse konnte nicht gefunden werden: %s (%s)" % (adress_text, fehler))
            self._als_fehlend_melden(
                rolle, name, adress_text,
                "%s: %s" % (type(fehler).__name__, fehler),
            )
            return None
        # Ein erfolgreich beantworteter Aufruf ohne Treffer bleibt im Cache.
        self.cache[adress_text] = None
        self.geaendert = True
        self._als_fehlend_melden(
            rolle, name, adress_text, "Kein Nominatim-Treffer"
        )
        return None

    def save_data(self):
        """Speichert neue Koordinaten und die Liste fehlender Standorte."""
        # Nur neue Suchergebnisse schreiben. So bleiben vorhandene Korrekturen erhalten.
        if self.geaendert:
            KOORDINATEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            KOORDINATEN_CACHE.write_text(
                json.dumps(self.cache, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        FEHLENDE_ADRESSEN.parent.mkdir(parents=True, exist_ok=True)
        # Der Bericht wird bei jedem Lauf neu erstellt und zeigt den aktuellen Stand.
        with FEHLENDE_ADRESSEN.open("w", encoding="utf-8", newline="") as datei:
            schreiber = csv.writer(datei)
            schreiber.writerow(("typ", "name", "adresse", "fehler"))
            schreiber.writerows(sorted(self.fehlende))
        print("Fehlende Adressen: %d (%s)" % (len(self.fehlende), FEHLENDE_ADRESSEN))


def punkte_laden():
    """Liefert Schulen, Schulämter und Träger mit nutzbaren Standorten."""
    # Überschreibt Adressen manuell aus der Excel-Tabelle mit den
    # Angaben in overrides.json. 
    korrekturen = {}
    for eintrag in json.loads(
        (DATEN / "overrides.json").read_text(encoding="utf-8")
    )["entries"]:
        # Alte Träger-Einträge bleiben ohne Anpassung gültig. Neue Einträge
        # können über Typ und Name auch Schulen, Schulämter oder Verwaltungen
        # korrigieren.
        if "carrier" in eintrag:
            korrekturen[("Schulträger", eintrag["carrier"].strip())] = eintrag
        elif "type" in eintrag and "name" in eintrag:
            korrekturen[(eintrag["type"], eintrag["name"].strip())] = eintrag
    standortsuche = Standortsuche()
    schulen, schulaemter, traeger = [], {}, {}
    bekannte_aemter, bekannte_traeger = set(), set()

    # Pro Schulamt und Träger zählt nur die erste Zeile. Schulen werden
    # dagegen in jeder passenden Zeile erfasst.
    for zeile in excel_zeilen_lesen():
        if not isinstance(zeile.get("sh_scht_name"), str):
            continue

        amtsname = zeile.get("sh_scha_name")
        if isinstance(amtsname, str) and amtsname not in bekannte_aemter:
            bekannte_aemter.add(amtsname)
            korrektur = korrekturen.get(("Schulamt", amtsname.strip()), {})
            amtsadresse = korrektur.get("address") or adresse(zeile, "scha")
            punkt = standortsuche.finden(
                amtsadresse, "Schulamt", amtsname, korrektur.get("coordinates")
            )
            if punkt:
                schulaemter[amtsname] = {"name": amtsname, "punkt": punkt}

        name = zeile["sh_scht_name"]
        if name not in bekannte_traeger:
            bekannte_traeger.add(name)
            korrektur = korrekturen.get(("Schulträger", name.strip()), {})
            # Eine korrigierte Adresse ersetzt die Excel-Adresse. Korrigierte
            # Koordinaten werden von der Standortsuche direkt übernommen.
            traeger_adresse = korrektur.get("address") or adresse(zeile, "scht")
            punkt = standortsuche.finden(traeger_adresse, "Schulträger", name,
                                         korrektur.get("coordinates"))
            verwaltung = zeile.get("sh_scht_verwaltet")
            verwaltungs_punkt = None
            verwaltungs_adresse = adresse(zeile, "scht_verwaltet")
            if isinstance(verwaltung, str) and verwaltungs_adresse:
                verwaltungs_korrektur = korrekturen.get(
                    ("Verwaltung", verwaltung.strip()), {}
                )
                verwaltungs_adresse = (
                    verwaltungs_korrektur.get("address") or verwaltungs_adresse
                )
                verwaltungs_punkt = standortsuche.finden(
                    verwaltungs_adresse, "Verwaltung", verwaltung,
                    korrektur.get("manager_coordinates")
                    or verwaltungs_korrektur.get("coordinates"),
                )
            if punkt:
                traeger[name] = {
                    "name": name,
                    "punkt": punkt,
                    "verwaltung": verwaltung,
                    "verwaltungs_punkt": verwaltungs_punkt,
                    # "X" kennzeichnet eine externe Verwaltung ohne eigene
                    # Eigenschaft als Schulträger.
                    "reine_verwaltung": str(zeile.get(
                        "sh_scht_verwaltet - externe Verwaltung ohne SchT-Eigenschaft"
                    )).strip().upper() == "X",
                }

        # Anders als beim Träger kann in jeder Zeile eine Schule stehen.
        schulname = zeile.get("sh_schule_name")
        if isinstance(schulname, str):
            korrektur = korrekturen.get(("Schule", schulname.strip()), {})
            schuladresse = korrektur.get("address") or adresse(zeile, "schule")
            punkt = standortsuche.finden(
                schuladresse, "Schule", schulname, korrektur.get("coordinates")
            )
            if punkt:
                schulen.append({"name": schulname, "punkt": punkt,
                                "art": zeile.get("sh_schule_art") or "",
                                "traeger": zeile["sh_scht_name"]})

    standortsuche.save_data()
    print("Schulen: %d, Schulämter: %d, Schulträger: %d" %
          (len(schulen), len(schulaemter), len(traeger)))
    return schulen, list(schulaemter.values()), list(traeger.values())
