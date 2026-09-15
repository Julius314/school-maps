"""Erstellt sieben PNG-Karten mit denselben Themen wie die interaktive Karte."""

import math
from collections import defaultdict

import contextily as cx
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.markers import MarkerStyle
from matplotlib.transforms import offset_copy
from pyproj import Transformer
import requests
from shapely.geometry import MultiPoint
from shapely.ops import unary_union

from map_data import DATEN, ORDNER, punkte_laden


AUSGABE = ORDNER / "output"
KACHELN = ORDNER / "cache" / "contextily"

# Längen- und Breitengrade werden für Flächen und den Esri-Hintergrund
# in dieselben Kartenkoordinaten umgerechnet.
PROJEKTION = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
KACHEL_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
            "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}")
BILD_BREITE_ZOLL = 11
BILD_HOEHE_ZOLL = 13
BILD_DPI = 220
HINTERGRUNDFARBE = "#f3f3f3"
LILA = "#8e44ad"
ROSA = "#b824a4"
DREIECK_FARBE = "#c84d13"

TITEL = {
    1: "Kreise",
    2: "Schulämter",
    3: "Alle allgemeinbildenden Schulen",
    4: "Untere Schulaufsicht",
    5: "Obere Schulaufsicht",
    6: "Externe Verwaltung",
    7: "Schulträgergebiete",
}


def kartenkoordinaten(punkt):
    """Rechnet Längen- und Breitengrad in Kartenkoordinaten um."""
    return PROJEKTION(punkt[0], punkt[1])


def kreise_laden():
    """Liest Kreisgrenzen und fasst Teile mit gleichem Namen zusammen."""
    # Ein Kreis kann aus mehreren getrennten Flächen bestehen, etwa wegen Inseln.
    kreise = gpd.read_file(DATEN / "kreise.geojson").to_crs("EPSG:3857")
    return kreise.dissolve(by="GEN").geometry.to_dict()


def kartenausschnitt(kreise):
    """Bestimmt einen gemeinsamen Ausschnitt für alle sieben Karten."""
    vereinigung = unary_union(list(kreise.values()))
    x0, y0, x1, y1 = vereinigung.bounds
    # Derselbe Ausschnitt erleichtert den Vergleich, auch ohne Kreisgrenzen.
    rand_x, rand_y = (x1 - x0) * 0.025, (y1 - y0) * 0.025
    x0, x1, y0, y1 = x0 - rand_x, x1 + rand_x, y0 - rand_y, y1 + rand_y
    # Die Ausgabe ist 11 mal 13 Zoll groß. Bei Bedarf kommt an der
    # schmaleren Seite mehr Raum hinzu, damit nichts gestaucht wird.
    seitenverhaeltnis = BILD_BREITE_ZOLL / BILD_HOEHE_ZOLL
    breite, hoehe = x1 - x0, y1 - y0
    if breite / hoehe < seitenverhaeltnis:
        zugabe = (hoehe * seitenverhaeltnis - breite) / 2
        x0, x1 = x0 - zugabe, x1 + zugabe
    else:
        zugabe = (breite / seitenverhaeltnis - hoehe) / 2
        y0, y1 = y0 - zugabe, y1 + zugabe
    return x0, x1, y0, y1


def neue_abbildung(ausschnitt, titel):
    # DPI gibt die Bildpunkte pro Zoll an. Die Größe in Zoll bestimmt die Gesamtauflösung.
    abbildung, ax = plt.subplots(figsize=(BILD_BREITE_ZOLL, BILD_HOEHE_ZOLL),
                                 dpi=BILD_DPI)
    abbildung.subplots_adjust(left=0, right=1, bottom=0, top=0.94)
    abbildung.text(0.5, 0.975, titel, ha="center", va="center",
                   fontsize=18, weight="bold", color="#2c3e50")
    ax.set_xlim(ausschnitt[0], ausschnitt[1])
    ax.set_ylim(ausschnitt[2], ausschnitt[3])
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_facecolor(HINTERGRUNDFARBE)
    return abbildung, ax


def hintergrund_zeichnen(ax, zoom=9):
    """Lädt die Esri-Hintergrundkarte und speichert Bildteile für spätere Läufe."""
    cx.set_cache_dir(KACHELN)
    try:
        cx.add_basemap(ax, source=KACHEL_URL, zoom=zoom, attribution=False,
                       interpolation="bilinear", zorder=-10, timeout=8)
    except requests.RequestException:
        print("Esri-Hintergrund nicht erreichbar. Die Karte bleibt grau.")


def kreis_ebene(ax, kreise, schulamt=False):
    """Zeichnet Kreise oder Schulamtsgebiete mit Beschriftung."""
    farbe = "#2980b9" if schulamt else "#2c3e50"
    gpd.GeoSeries(list(kreise.values()), crs="EPSG:3857").plot(
        ax=ax, edgecolor=farbe, facecolor=to_rgba(farbe, 0.05),
        linewidth=1, zorder=2,
    )
    for name, geometrie in kreise.items():
        # Ein Punkt innerhalb der Fläche für das Label.
        punkt = geometrie.representative_point()
        beschriftung = ("Schulamt " if schulamt else "") + name
        ax.text(punkt.x, punkt.y, beschriftung, ha="center", va="center",
                fontsize=7, color="#496078", weight="semibold", zorder=9)


def schulfarbe(art):
    """Ordnet der Schulart dieselbe Farbe wie in der interaktiven Karte zu."""
    # GS steht für Grundschule, Gem für Gemeinschaftsschule, GY für
    # Gymnasium. Schulen mit GS und Gem bekommen ein zweifarbiges Zeichen.
    if "GS" in art and "Gem" in art:
        return "gemischt"
    if "GY" in art:
        return "#e74c3c"
    if "GemOSt" in art:
        return "#e67e22"
    if "Gem" in art:
        return "#f1c40f"
    if "GS" in art:
        return "#2ecc71"
    return "#95a5a6"


def schul_ebene(ax, schulen):
    """Zeichnet Schulstandorte als farbige Punkte."""
    geteilter_kreis = MarkerStyle("o", fillstyle="left")
    for schule in schulen:
        x, y = kartenkoordinaten(schule["punkt"])
        farbe = schulfarbe(schule["art"])
        if farbe == "gemischt":
            # Eine Kreishälfte ist gelb, die andere grün.
            ax.plot([x], [y], linestyle="", marker=geteilter_kreis,
                    markersize=5, markerfacecolor="#f1c40f",
                    markerfacecoloralt="#2ecc71", markeredgecolor="white",
                    markeredgewidth=0.8, zorder=6)
        else:
            ax.scatter([x], [y], s=18, c=[farbe], edgecolors="white",
                       linewidths=0.5, zorder=6)


def gleicher_standort(traeger):
    """Prüft, ob Schulträger und Verwaltung am selben Ort liegen."""
    verwaltungs_punkt = traeger["verwaltungs_punkt"]
    # Eine kleine Abweichung in den Koordinaten soll keinen zweiten
    # Standort oder eine fast unsichtbare Verbindung erzeugen.
    return (verwaltungs_punkt is not None and
            math.dist(traeger["punkt"], verwaltungs_punkt) < 0.00001)


def traeger_ebene(ax, traeger):
    """Zeichnet Träger und Verwaltungsstandorte als getrennte Symbole."""
    # Verwaltungsdreiecke am selben Ort werden nur einmal gezeichnet,
    # auch wenn mehrere Träger auf diese Verwaltung verweisen.
    gemeinsame_punkte = {tuple(eintrag["punkt"]) for eintrag in traeger
                         if eintrag["verwaltung"] and gleicher_standort(eintrag)}
    reine_verwaltungs_punkte = {
        tuple(eintrag["verwaltungs_punkt"]) for eintrag in traeger
        if eintrag["reine_verwaltung"] and eintrag["verwaltung"] and
        eintrag["verwaltungs_punkt"] and not gleicher_standort(eintrag)
    }
    # Der Versatz betrifft nur das Symbol, nicht den geografischen Standort.
    dreieck_oberhalb = offset_copy(ax.transData, fig=ax.figure,
                                  y=4, units="points")
    for eintrag in traeger:
        x, y = kartenkoordinaten(eintrag["punkt"])
        ax.scatter([x], [y], s=23, c=[LILA], marker="s",
                   edgecolors="white", linewidths=0.6, zorder=6)

    for punkt in gemeinsame_punkte:
        x, y = kartenkoordinaten(punkt)
        ax.scatter([x], [y], s=14, c=[ROSA], marker="^", zorder=8,
                   transform=dreieck_oberhalb)

    for punkt in reine_verwaltungs_punkte:
        x, y = kartenkoordinaten(punkt)
        ax.scatter([x], [y], s=40, c=[DREIECK_FARBE], marker="^", zorder=9)


def verwaltungs_ebene(ax, traeger):
    """Zeichnet Verbindungen zwischen Trägern und externen Verwaltungen."""
    # Bei einer reinen externen Verwaltung verläuft die Linie vom Träger
    # zur Verwaltung. Sonst zeigt ein Pfeil von der Verwaltung zum Träger.
    gezeichnete_verbindungen = set()
    for eintrag in traeger:
        verwaltung = eintrag["verwaltung"]
        verwaltungs_punkt = eintrag["verwaltungs_punkt"]
        if not (verwaltung and verwaltungs_punkt) or gleicher_standort(eintrag):
            continue
        reine_verwaltung = eintrag["reine_verwaltung"]
        start = eintrag["punkt"] if reine_verwaltung else verwaltungs_punkt
        ende = verwaltungs_punkt if reine_verwaltung else eintrag["punkt"]
        verbindung = (tuple(start), tuple(ende), reine_verwaltung)
        # Gleiche Standorte ergeben dieselbe Linie. Einmal zeichnen reicht.
        if verbindung in gezeichnete_verbindungen:
            continue
        gezeichnete_verbindungen.add(verbindung)

        anfang_x, anfang_y = kartenkoordinaten(start)
        ende_x, ende_y = kartenkoordinaten(ende)
        if reine_verwaltung:
            # Reine Verwaltungen haben keinen Pfeilkopf.
            ax.plot([anfang_x, ende_x], [anfang_y, ende_y],
                    color=ROSA, linewidth=1.8, alpha=0.85, zorder=5)
        else:
            ax.annotate("", xy=(ende_x, ende_y), xytext=(anfang_x, anfang_y),
                        arrowprops={"arrowstyle": "-|>", "color": ROSA,
                                    "lw": 1.8, "mutation_scale": 7}, zorder=5)


def traegergebiete_ebene(ax, schulen, traeger):
    """Umrandet pro Träger dessen Schulen und, falls bekannt, dessen Sitz."""
    sitze = {eintrag["name"]: kartenkoordinaten(eintrag["punkt"])
             for eintrag in traeger}
    gruppen = defaultdict(list)
    for schule in schulen:
        gruppen[schule["traeger"]].append(kartenkoordinaten(schule["punkt"]))
    huellen = []
    for name, punkte in gruppen.items():
        if name in sitze:
            punkte.append(sitze[name])
        # Die kleinste umhüllende Form wird etwas verbreitert, damit auch
        # ein einzelner Standort sichtbar ist. Sie ist keine Amtsgrenze.
        huellen.append(MultiPoint(punkte).convex_hull.buffer(1000))
    if huellen:
        gpd.GeoSeries(huellen, crs="EPSG:3857").plot(
            ax=ax, edgecolor=LILA, facecolor=to_rgba(LILA, 0.15),
            linewidth=1, linestyle="--", zorder=3,
        )


def speichern(abbildung, name):
    pfad = AUSGABE / name
    abbildung.savefig(pfad, dpi=BILD_DPI, facecolor=HINTERGRUNDFARBE)
    plt.close(abbildung)
    print("Gespeichert:", pfad)


def main():
    """Erstellt die sieben Karten mit gemeinsamem Ausschnitt."""
    AUSGABE.mkdir(exist_ok=True)
    schulen, _schulaemter, traeger = punkte_laden()
    kreise = kreise_laden()
    ausschnitt = kartenausschnitt(kreise)

    # Die Karten werden in der Reihenfolge der interaktiven Karte erstellt.
    for kartennummer in TITEL:
        abbildung, ax = neue_abbildung(ausschnitt, TITEL[kartennummer])
        hintergrund_zeichnen(ax)
        # Die Nummer bestimmt die sichtbaren Themen. Die Karte selbst
        # wird jedes Mal auf demselben Ausschnitt aufgebaut.
        if kartennummer in (1, 3, 5):
            kreis_ebene(ax, kreise)
        if kartennummer in (2, 4):
            kreis_ebene(ax, kreise, schulamt=True)
        if kartennummer == 3:
            schul_ebene(ax, schulen)
        if kartennummer == 4:
            schul_ebene(ax, [s for s in schulen if "GS" in s["art"] or
                          "Gem" in s["art"]])
        if kartennummer == 5:
            schul_ebene(ax, [s for s in schulen if "GY" in s["art"] or
                          "GemOSt" in s["art"]])
        if kartennummer == 6:
            verwaltungs_ebene(ax, traeger)
            traeger_ebene(ax, traeger)
        if kartennummer == 7:
            traegergebiete_ebene(ax, schulen, traeger)
        speichern(abbildung, "karte%d.png" % kartennummer)


if __name__ == "__main__":
    main()
