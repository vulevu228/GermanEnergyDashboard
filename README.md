# German Energy Dashboard

A small Python pipeline that pulls seven-plus years of Germany's electricity data
from the **energy-charts.info** API (run by Fraunhofer ISE), saves it as Parquet,
and feeds a Power BI report covering the generation mix, wholesale prices,
cross-border trade and installed capacity.

Coverage: **January 2019 – 7 September 2026** (so 2026 is a partial year). Generation
is 15-minute resolution, prices are hourly.

## Why

Germany is running the biggest energy transition ("Energiewende") of any large
economy, and all of it shows up in public data: the 2022 gas-price shock, the last
nuclear plants switching off, solar capacity more than doubling, and negative
electricity prices going from rare to routine. This project turns the raw API into
something you can actually read.

## The data

Everything comes from `https://api.energy-charts.info` — **no API key, no signup.**
Four endpoints, one Parquet file each:

| File | Endpoint | What's in it |
| --- | --- | --- |
| `data/de_public_power.parquet` | `/public_power` | Net generation by source (wind, solar, coal, gas, nuclear, …) plus Load and the renewable-share series, every 15 min |
| `data/de_price.parquet` | `/price` | Day-ahead wholesale price, EUR/MWh, bidding zone `DE-LU`, hourly |
| `data/de_cbet.parquet` | `/cbet` | Cross-border scheduled trade in GW, one column per neighbour (+ = import to Germany, − = export) |
| `data/de_installed_power_monthly.parquet`, `..._yearly.parquet` | `/installed_power` | Installed capacity per source, GW, month-end and year-end |

The Parquet files are small (~25 MB total) so they're committed straight to the
repo — no separate download needed. Data is CC BY 4.0; credit goes to
**Bundesnetzagentur | SMARD.de** and **Energy-Charts.info (Fraunhofer ISE)**.

## The pipeline

`fetch_energy_charts.py` is the whole ETL. Each endpoint gets a small function
(`public_power`, `price`, `cbet`, `installed_power`) that fetches the JSON, turns
the `unix_seconds + [{name, data}]` shape into a tidy DataFrame, and converts
timestamps to `Europe/Berlin`.

A few things worth knowing:

- **Rate limit.** The API allows about 2 requests per minute. The script sleeps
  35 s between calls and, if it still gets an HTTP 429, waits out the `Retry-After`
  header before trying again.
- **Chunking.** The time-series endpoints are pulled one calendar year at a time,
  then glued together. A full 2019–2026 run takes roughly 15 minutes because of
  the sleeps.
- **Parquet, not CSV.** Columnar, compressed, keeps the dtypes and the timezone,
  and both pandas and Power BI load it with no re-parsing.

## Running it

```bash
pip install -r requirements.txt
python fetch_energy_charts.py
```

Quick check without the full run:

```python
from fetch_energy_charts import public_power
public_power("de", "2025-01-01", "2025-01-31").head()
```

## The Power BI report

`energie-daten-DE.pbix` — open it in Power BI Desktop (free). Rough build:

- **Power Query** loads the Parquet files, unpivots the wide source columns into a
  long `source / value` table, and buckets sources into Renewable / Fossil / Nuclear.
- **Star schema**: a date table joined to fact tables for generation, price, trade
  and capacity.
- **DAX** measures for renewable share, year-over-year generation, average price
  captured, and rolling annual totals.

To refresh it, re-run the Python pull first, then point the Power Query source at
your local `data/` folder.

## What the numbers say

All figures are from this dataset. **2026 is year-to-date (through 7 Sep).**

**The 2022 price shock.** Average day-ahead price by year: €38 (2019) → €31 (2020)
→ €97 (2021) → **€235 (2022)** → €95 (2023) → €79 (2024) → €91 (2025) → €104 (2026
YTD). The 2022 peak is about **8x** the 2020 low. Europe's "merit order" market
lets the most expensive plant needed set the price for everyone, so when Russian
gas was cut off, record gas prices dragged the whole power market up with them.

**Nuclear went to zero.** Nuclear output: 71 TWh (2019) → 33 TWh (2022) → 7 TWh
(2023) → **0 from 2024 on**. The last three reactors shut in April 2023. Renewables
and lower demand covered the gap, not new fossil plants.

**Renewables passed 60%.** Renewable share of public generation climbed from **~44%
(2019) to ~61% (2024–2026)**. The engine is solar: generation went 42 → 70 TWh
while installed solar capacity went **46 → 118 GW**. Onshore wind capacity rose
53 → 71 GW, offshore 7.7 → 11 GW. Fossil generation fell ~208 → ~150 TWh.

**Negative prices are the new normal.** Hours with a negative wholesale price:
**211 (2019) → 301 (2023) → 724 (2025) → 1,773 (2026 YTD)**. Midday solar now
regularly pushes supply past demand faster than coal and gas plants can throttle
down. This is the catch in the transition: more renewable capacity, less money
earned per MWh.

**The winter heartbeat.** Renewable *and* fossil output both peak in Q4/Q1 and dip
in Q2/Q3. Winter demand (heating, lighting) is much higher, German wind blows
hardest in winter storms, and conventional plants still ramp up alongside the wind
to cover whatever load is left.

**Cross-border balancing.** Germany trades non-stop with Denmark, France, the
Netherlands, Norway and Switzerland — dumping surplus wind when it's stormy,
pulling in French nuclear and Nordic hydro during low-wind "Dunkelflaute" spells.

## Notes and caveats

- 2026 is a partial year — don't read its totals as if it were finished.
- `/public_power` is *public* net generation; it leaves out industrial self-supply,
  so it slightly understates total national generation.
- Prices are for the `DE-LU` (Germany–Luxembourg) bidding zone.

## Stack

Python (requests, pandas, pyarrow) · Apache Parquet · Power BI Desktop (Power
Query, star schema, DAX)
