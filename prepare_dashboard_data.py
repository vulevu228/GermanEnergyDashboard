"""
Bereitet die Rohdaten aus data/ für das Power-BI-Dashboard vor.

Die Rohdateien haben 15-Minuten-Werte in MW (über 5 Mio. Zeilen nach dem
Entpivotieren). Das Dashboard braucht Energie (GWh/TWh) pro Tag. Dieses Skript
rechnet das einmal in Python aus und schreibt kleine Tabellen nach
data/dashboard/. Power BI lädt nur diese Dateien.

Start:  python prepare_dashboard_data.py   (nach fetch_energy_charts.py)
"""
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DATA = Path(__file__).resolve().parent / "data"
OUT = DATA / "dashboard"

# Quelle in public_power -> (Name im Dashboard, Gruppe, Sortierung)
SOURCES = {
    "Solar": ("Solar", "Renewables", 1),
    "Wind onshore": ("Wind onshore", "Renewables", 2),
    "Wind offshore": ("Wind offshore", "Renewables", 3),
    "Biomass": ("Biomass & hydro", "Renewables", 4),
    "Hydro Run-of-River": ("Biomass & hydro", "Renewables", 4),
    "Hydro water reservoir": ("Biomass & hydro", "Renewables", 4),
    "Geothermal": ("Biomass & hydro", "Renewables", 4),
    "Nuclear": ("Nuclear", "Nuclear", 5),
    "Fossil brown coal / lignite": ("Coal", "Fossil", 6),
    "Fossil hard coal": ("Coal", "Fossil", 6),
    "Fossil gas": ("Gas", "Fossil", 7),
    "Fossil coal-derived gas": ("Gas", "Fossil", 7),
    "Fossil oil": ("Other", "Fossil", 8),
    "Others": ("Other", "Fossil", 8),
    "Waste": ("Other", "Fossil", 8),
    "Hydro pumped storage": ("Other", "Storage", 8),
}
GROUP_ORDER = {"Renewables": 1, "Nuclear": 2, "Fossil": 3, "Storage": 4}


def hourly(df):
    """Mittelwert pro Stunde (lokale Zeit). MW x 1 h = MWh, egal ob die Rohdaten 15 min oder 1 h haben."""
    return df.resample("1h").mean()


def local_date(idx):
    return pd.to_datetime(idx.tz_localize(None).date)


def generation_daily(pp):
    h = hourly(pp[list(SOURCES)].fillna(0)).clip(lower=0)
    h["date"] = local_date(h.index)
    daily = h.groupby("date").sum() / 1000  # MWh -> GWh
    long = daily.reset_index().melt("date", var_name="raw", value_name="gwh")
    long["source"] = long["raw"].map(lambda s: SOURCES[s][0])
    long["group"] = long["raw"].map(lambda s: SOURCES[s][1])
    long = long.groupby(["date", "source", "group"], as_index=False)["gwh"].sum()
    long["source_order"] = long["source"].map({v[0]: v[2] for v in SOURCES.values()})
    long["group_order"] = long["group"].map(GROUP_ORDER)
    return long


def power_daily(pp, price):
    h = hourly(pp[["Load", "Residual load", "Cross border electricity trading"]])
    h["date"] = local_date(h.index)
    d = h.groupby("date").sum() / 1000
    d.columns = ["load_gwh", "residual_load_gwh", "net_import_gwh"]  # + = Import, - = Export
    # price_sum / price_hours = zeitgewichteter Mittelpreis (EUR/MWh)

    # Seit 1. Okt. 2025 gibt es Viertelstunden-Preise, vorher Stundenpreise. Jede Zeile zählt darum mit
    # ihrer Dauer (0,25 h oder 1 h) - sonst würden 4 Viertelstunden als 4 "Stunden" gezählt.
    p = price[["price_eur_mwh"]].dropna().copy()
    step = p.index.to_series().diff().shift(-1).dt.total_seconds().div(3600)
    p["dur"] = step.where(step.isin([0.25, 1.0])).ffill().fillna(1.0)
    p["weighted"] = p["price_eur_mwh"] * p["dur"]
    p["neg_dur"] = p["dur"].where(p["price_eur_mwh"] < 0, 0)
    p["date"] = local_date(p.index)
    pd_ = p.groupby("date").agg(price_sum=("weighted", "sum"), price_hours=("dur", "sum"),
                                price_min=("price_eur_mwh", "min"), price_max=("price_eur_mwh", "max"),
                                negative_hours=("neg_dur", "sum"))
    return d.join(pd_, how="outer").reset_index()


def hourly_profile(pp, price):
    """Pro Monat und Stunde des Tages: Summen + Anzahl, damit Power BI echte Mittelwerte bilden kann."""
    h = hourly(pp[["Solar", "Wind onshore", "Wind offshore", "Load"]])
    h["wind"] = h["Wind onshore"] + h["Wind offshore"].fillna(0)
    h = h.join(hourly(price[["price_eur_mwh"]]))
    h["month"] = pd.to_datetime(h.index.tz_localize(None).to_period("M").to_timestamp())
    h["hour"] = h.index.hour
    g = h.groupby(["month", "hour"]).agg(solar_mwh=("Solar", "sum"), wind_mwh=("wind", "sum"), load_mwh=("Load", "sum"),
                                         power_hours=("Load", "count"), price_sum=("price_eur_mwh", "sum"),
                                         price_hours=("price_eur_mwh", "count"))
    return g.reset_index()


def trade_daily(cbet):
    h = hourly(cbet.drop(columns=["sum"]))
    h["date"] = local_date(h.index)
    d = h.groupby("date").sum(min_count=1)  # GW x h = GWh
    long = d.reset_index().melt("date", var_name="country", value_name="net_gwh").dropna()
    return long


def capacity(monthly, yearly):
    m = monthly.rename(columns={"Solar AC": "Solar"}).drop(columns=["Solar DC", "Battery storage (capacity)"])
    m = m.rename(columns={"Battery storage (power)": "Battery storage"})
    cm = m.reset_index().melt("month", var_name="technology", value_name="gw").dropna()
    cm = cm[cm["month"] >= "2019-01-01"]  # das Dashboard beginnt 2019

    y = yearly.rename(columns={"Solar AC": "Solar", "Battery storage (power)": "Battery storage",
                               "Fossil brown coal / lignite": "Lignite", "Fossil hard coal": "Hard coal",
                               "Fossil gas": "Gas", "Fossil oil": "Oil",
                               "Solar planned (EEG 2023)": "Solar target",
                               "Wind onshore planned (EEG 2023)": "Wind onshore target",
                               "Wind offshore planned (WindSeeG)": "Wind offshore target"})
    y = y.drop(columns=["Solar DC", "Battery storage (capacity)"])
    cy = y.reset_index().rename(columns={"date": "year_start"}).melt("year_start", var_name="technology", value_name="gw").dropna()
    cy["year"] = cy["year_start"].dt.year
    cy["is_target"] = cy["technology"].str.endswith(" target").astype(int)
    return cm, cy


def simple_types(df):
    """Einfache Parquet-Typen, die Power BI sicher liest: string, int64, float64, Zeit in ms."""
    t = pa.Table.from_pandas(df, preserve_index=False)
    fields = []
    for f in t.schema:
        typ = f.type
        if pa.types.is_large_string(typ) or pa.types.is_string(typ):
            typ = pa.string()
        elif pa.types.is_integer(typ):
            typ = pa.int64()
        elif pa.types.is_timestamp(typ):
            typ = pa.timestamp("ms")
        fields.append(pa.field(f.name, typ))
    return t.cast(pa.schema(fields))


def main():
    OUT.mkdir(exist_ok=True)
    pp = pd.read_parquet(DATA / "de_public_power.parquet")
    # Nur ganze Tage: der letzte Tag der Rohdaten ist oft nur halb da und würde die Summen verfälschen.
    per_day = pp.groupby(local_date(pp.index)).size()
    end = per_day[per_day >= 92].index.max() + pd.Timedelta(days=1)  # 92 = Tag der Zeitumstellung im Frühling
    end = pd.Timestamp(end).tz_localize("Europe/Berlin")
    pp = pp[pp.index < end]
    price = pd.read_parquet(DATA / "de_price.parquet").loc[lambda d: d.index < end]
    cbet = pd.read_parquet(DATA / "de_cbet.parquet").loc[lambda d: d.index < end]
    print("Letzter ganzer Tag:", (end - pd.Timedelta(days=1)).date())
    cm, cy = capacity(pd.read_parquet(DATA / "de_installed_power_monthly.parquet"),
                      pd.read_parquet(DATA / "de_installed_power_yearly.parquet"))
    tables = {
        "generation_daily": generation_daily(pp),
        "power_daily": power_daily(pp, price),
        "hourly_profile": hourly_profile(pp, price),
        "trade_daily": trade_daily(cbet),
        "capacity_monthly": cm,
        "capacity_yearly": cy,
    }
    for name, df in tables.items():
        pq.write_table(simple_types(df), OUT / f"{name}.parquet")
        print(f"{name}: {len(df):,} Zeilen")


if __name__ == "__main__":
    main()
