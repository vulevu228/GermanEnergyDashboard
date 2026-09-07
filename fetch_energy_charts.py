"""
Pulls German electricity data from the energy-charts.info API (Fraunhofer ISE)
and saves it as Parquet files in ./data.

No API key needed. The API is rate limited to roughly 2 requests / minute, so
this script sleeps between calls and backs off on HTTP 429.
"""

import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://api.energy-charts.info"
OUT = Path("data")
OUT.mkdir(exist_ok=True)
PAUSE = 35  # seconds between calls -> stays under ~2 requests / minute


def get(path, **params):
    """GET a JSON endpoint, retrying politely on rate-limit (429)."""
    for _ in range(6):
        r = requests.get(f"{BASE}/{path}", params=params, timeout=90)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 30))
            print(f"  429 -> sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate-limited repeatedly on {path}")


def _timeseries(j, value_key="production_types"):
    """v1 shape: unix_seconds + [{name, data}] -> tidy DataFrame in Europe/Berlin."""
    idx = pd.to_datetime(j["unix_seconds"], unit="s", utc=True).tz_convert("Europe/Berlin")
    df = pd.DataFrame({item["name"]: item["data"] for item in j[value_key]}, index=idx)
    df.index.name = "timestamp"
    return df


def public_power(country, start, end):
    """15-minute net generation by source, plus load and renewable-share series."""
    return _timeseries(get("public_power", country=country, start=start, end=end))


def cbet(country, start, end):
    """Cross-border scheduled trade, GW per neighbour (+ import to DE / - export)."""
    return _timeseries(get("cbet", country=country, start=start, end=end), value_key="countries")


def price(bzn, start, end):
    """Hourly day-ahead wholesale price, EUR/MWh, for one bidding zone."""
    j = get("price", bzn=bzn, start=start, end=end)
    idx = pd.to_datetime(j["unix_seconds"], unit="s", utc=True).tz_convert("Europe/Berlin")
    return pd.DataFrame({"price_eur_mwh": j["price"]}, index=idx).rename_axis("timestamp")


def installed_power(country, time_step="monthly"):
    """Installed capacity per source, GW, at the end of each month or year."""
    j = get("installed_power", country=country, time_step=time_step,
            installation_decommission="false")
    idx = pd.to_datetime(j["time"], format="mixed")  # handles "01.2002" and "2028-01-01"
    df = pd.DataFrame({item["name"]: item["data"] for item in j["production_types"]}, index=idx)
    df.index.name = "date"
    return df


def pull_years(fn, years, *args, **kwargs):
    """Call a yearly-chunked fetcher once per year and stitch the results together."""
    frames = []
    for y in years:
        print(f"  {y}")
        frames.append(fn(*args, start=f"{y}-01-01", end=f"{y}-12-31", **kwargs))
        time.sleep(PAUSE)
    return pd.concat(frames).sort_index()


if __name__ == "__main__":
    YEARS = range(2019, 2027)

    print("public_power")
    pull_years(public_power, YEARS, "de").to_parquet(OUT / "de_public_power.parquet")

    print("price")
    pull_years(price, YEARS, "DE-LU").to_parquet(OUT / "de_price.parquet")

    print("cbet")
    pull_years(cbet, YEARS, "de").to_parquet(OUT / "de_cbet.parquet")

    print("installed_power")
    installed_power("de", "monthly").to_parquet(OUT / "de_installed_power_monthly.parquet")
    time.sleep(PAUSE)
    installed_power("de", "yearly").to_parquet(OUT / "de_installed_power_yearly.parquet")

    print("done ->", OUT.resolve())
