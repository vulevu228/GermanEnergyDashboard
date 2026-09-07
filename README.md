# Strommarkt-Dashboard Deutschland

Eine kleine Python-Pipeline, die über sieben Jahre deutscher Stromdaten von der
**energy-charts.info**-API (betrieben vom Fraunhofer ISE) abruft, als Parquet
speichert und in einen Power-BI-Report einspeist – Strommix, Großhandelspreise,
grenzüberschreitender Handel und installierte Leistung.

Zeitraum: **Januar 2019 – 7. September 2026** (2026 ist also ein Rumpfjahr). Die
Erzeugung liegt in 15-Minuten-Auflösung vor, die Preise stündlich.

## Das Dashboard

![Strom-Dashboard Deutschland, Überblick 2019–2026](images/dashboard-overview.png)

Jährliche Gesamterzeugung, die Kurve des durchschnittlichen Großhandelspreises,
der Strommix aus Erneuerbaren und konventioneller Erzeugung sowie der Stromhandel
mit den Nachbarländern. Der Datums-Slider oben steuert alle Visuals gleichzeitig –
so lässt sich die ganze Seite auf ein einzelnes Ereignis eingrenzen.

## Worum es geht

Deutschland stemmt die größte Energiewende aller großen Industrienationen, und
alles davon steckt in öffentlichen Daten: der Gaspreisschock 2022, die Abschaltung
der letzten Kernkraftwerke, die Verdopplung der Solarkapazität und negative
Strompreise, die von der Ausnahme zur Regel werden. Dieses Projekt macht aus der
rohen API etwas Lesbares.

## Die Daten

Alles kommt von `https://api.energy-charts.info` – **kein API-Key, keine Anmeldung.**
Vier Endpunkte, je eine Parquet-Datei:

| Datei | Endpunkt | Inhalt |
| --- | --- | --- |
| `data/de_public_power.parquet` | `/public_power` | Nettostromerzeugung nach Quelle (Wind, Solar, Kohle, Gas, Kernenergie, …) plus Last und die Erneuerbaren-Anteil-Reihen, im 15-Minuten-Takt |
| `data/de_price.parquet` | `/price` | Day-Ahead-Großhandelspreis, EUR/MWh, Gebotszone `DE-LU`, stündlich |
| `data/de_cbet.parquet` | `/cbet` | Grenzüberschreitender geplanter Handel in GW, eine Spalte je Nachbarland (+ = Import nach Deutschland, − = Export) |
| `data/de_installed_power_monthly.parquet`, `..._yearly.parquet` | `/installed_power` | Installierte Leistung nach Quelle, GW, zum Monats- bzw. Jahresende |

Die Parquet-Dateien sind klein (~25 MB insgesamt) und liegen direkt im Repo –
kein separater Download nötig. Die Daten stehen unter CC BY 4.0; Quellenangabe an
**Bundesnetzagentur | SMARD.de** und **Energy-Charts.info (Fraunhofer ISE)**.

## Die Pipeline

`fetch_energy_charts.py` ist die komplette ETL-Strecke. Jeder Endpunkt bekommt
eine kleine Funktion (`public_power`, `price`, `cbet`, `installed_power`), die das
JSON abruft, die Struktur `unix_seconds + [{name, data}]` in einen sauberen
DataFrame umbaut und die Zeitstempel nach `Europe/Berlin` umrechnet.

Ein paar Dinge, die man wissen sollte:

- **Rate-Limit.** Die API erlaubt etwa 2 Anfragen pro Minute. Das Skript wartet
  35 s zwischen den Aufrufen und, falls trotzdem ein HTTP 429 kommt, den im
  `Retry-After`-Header genannten Zeitraum ab, bevor es erneut versucht.
- **Chunking.** Die Zeitreihen-Endpunkte werden Kalenderjahr für Kalenderjahr
  abgerufen und danach zusammengefügt. Ein kompletter Lauf 2019–2026 dauert wegen
  der Wartezeiten rund 15 Minuten.
- **Parquet statt CSV.** Spaltenorientiert, komprimiert, behält Datentypen und
  Zeitzone – pandas und Power BI laden es ohne erneutes Parsen.

## Ausführen

```bash
pip install -r requirements.txt
python fetch_energy_charts.py
```

Schneller Test ohne den kompletten Lauf:

```python
from fetch_energy_charts import public_power
public_power("de", "2025-01-01", "2025-01-31").head()
```

## Aufbau des Reports

`energie-daten-DE.pbix` – zu öffnen in Power BI Desktop (kostenlos). Grober Aufbau:

- **Power Query** lädt die Parquet-Dateien, wandelt die breiten Quellen-Spalten
  per Unpivot in eine lange `source / value`-Tabelle um und gruppiert die Quellen
  in Erneuerbar / Fossil / Kernenergie.
- **Sternschema**: eine Datumstabelle, verknüpft mit Faktentabellen für Erzeugung,
  Preis, Handel und Leistung.
- **DAX**-Measures für Erneuerbaren-Anteil, Erzeugung im Jahresvergleich,
  durchschnittlich erzielten Preis und rollierende Jahreswerte.

Zum Aktualisieren zuerst den Python-Abruf erneut laufen lassen, dann die
Power-Query-Quelle auf den lokalen `data/`-Ordner zeigen lassen.

## Was die Zahlen zeigen

Alle Werte stammen aus diesem Datensatz. **2026 ist ein laufendes Jahr (Stand
7. September).**

**Der Preisschock 2022.** Durchschnittlicher Day-Ahead-Preis nach Jahr: 38 €
(2019) → 31 € (2020) → 97 € (2021) → **235 € (2022)** → 95 € (2023) → 79 € (2024)
→ 91 € (2025) → 104 € (2026 lfd.). Die Spitze 2022 liegt rund **8-mal** über dem
Tief von 2020. Die europäische Merit-Order sorgt dafür, dass das teuerste noch
benötigte Kraftwerk den Preis für alle setzt – als russisches Gas wegfiel, zogen
die Rekord-Gaspreise den gesamten Strommarkt nach oben.

![Dashboard gefiltert auf die Preiskrise 2021–2023](images/dashboard-2021-2023-crisis.png)

*Derselbe Report, gefiltert auf Sep 2021 – Dez 2023: Die Preislinie läuft von
174 € über 235 € auf 98 €/MWh.*

**Kernenergie auf null.** Kernkraft-Erzeugung: 71 TWh (2019) → 33 TWh (2022) →
7 TWh (2023) → **0 ab 2024**. Die letzten drei Reaktoren gingen im April 2023 vom
Netz. Die Lücke schlossen Erneuerbare und ein geringerer Verbrauch, nicht neue
fossile Kraftwerke.

**Erneuerbare über 60 %.** Der Anteil der Erneuerbaren an der öffentlichen
Nettostromerzeugung stieg von **~44 % (2019) auf ~61 % (2024–2026)**. Motor ist
die Solarenergie: Erzeugung von 42 auf 70 TWh, während die installierte
Solarleistung von **46 auf 118 GW** wuchs. Die Onshore-Windleistung stieg von 53
auf 71 GW, Offshore von 7,7 auf 11 GW. Die fossile Erzeugung sank von ~208 auf
~150 TWh.

![Dashboard mit nur konventioneller Erzeugung, 2019–2026](images/dashboard-fossil-decline.png)

*Nur die konventionelle Erzeugung: Der fossile Block zeigt über den gesamten
Zeitraum nach unten.*

**Negative Preise sind der neue Normalfall.** Stunden mit negativem
Großhandelspreis: **211 (2019) → 301 (2023) → 724 (2025) → 1.773 (2026 lfd.)**.
Mittags drückt die Solarenergie das Angebot inzwischen regelmäßig über die
Nachfrage, schneller als Kohle- und Gaskraftwerke herunterregeln können. Das ist
der Haken an der Energiewende: mehr Erneuerbaren-Kapazität, weniger Erlös je MWh.

**Der Winter-Herzschlag.** Erneuerbare *und* fossile Erzeugung erreichen beide im
4./1. Quartal ihr Maximum und im 2./3. Quartal ihr Minimum. Der Winterverbrauch
(Heizen, Beleuchtung) ist deutlich höher, deutscher Wind weht in Winterstürmen am
stärksten, und konventionelle Kraftwerke fahren trotzdem parallel zum Wind hoch,
um die verbleibende Last zu decken.

**Grenzüberschreitender Ausgleich.** Deutschland handelt ununterbrochen mit
Dänemark, Frankreich, den Niederlanden, Norwegen und der Schweiz – exportiert
überschüssigen Windstrom bei Sturm und holt bei Dunkelflaute französischen Atom-
und skandinavischen Wasserkraftstrom herein.

## Hinweise und Einschränkungen

- 2026 ist ein Rumpfjahr – die Jahreswerte nicht wie ein abgeschlossenes Jahr
  lesen.
- `/public_power` ist die *öffentliche* Nettostromerzeugung; die industrielle
  Eigenversorgung fehlt, daher liegt sie leicht unter der gesamten nationalen
  Erzeugung.
- Die Preise gelten für die Gebotszone `DE-LU` (Deutschland–Luxemburg).

## Stack

Python (requests, pandas, pyarrow) · Apache Parquet · Power BI Desktop (Power
Query, Sternschema, DAX)
