# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
#     "pytrends",
#     "urllib3<2",
# ]
# ///
"""Fetch Google Trends daily interest for every celebrity in the deaths CSV.

Batched in cohorts of up to 5 names whose death dates fit inside a 120-day span,
queried over a window that gives daily granularity (≤270 days). One cohort = one
pytrends call. Caches the consolidated result to gtrends_cache.csv and records
any per-cohort failures to gtrends_failed.csv.
"""

import sys
import time
import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

PRE_DAYS = 30           # days before each celeb's death to include
POST_DAYS = 100         # days after each celeb's death to include
MAX_PER_COHORT = 5      # Trends payload limit
MAX_SPAN_DAYS = 120     # max gap between earliest/latest death in a cohort
                        # PRE_DAYS + MAX_SPAN_DAYS + POST_DAYS = 250 ≤ 269 (daily threshold)
BASE_SLEEP = 8          # seconds between successful cohort requests
MAX_RETRIES = 4         # retries on rate-limit / transient errors


def make_cohorts(deaths_df):
    """Greedy bin by death date — pack up to MAX_PER_COHORT consecutive deaths
    so long as latest - earliest ≤ MAX_SPAN_DAYS."""
    rows = deaths_df.sort_values("date").to_dict("records")
    cohorts, current = [], []
    for row in rows:
        if not current:
            current = [row]
            continue
        span = (row["date"] - current[0]["date"]).days
        if len(current) >= MAX_PER_COHORT or span > MAX_SPAN_DAYS:
            cohorts.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        cohorts.append(current)
    return cohorts


def fetch_with_retry(pt, names, timeframe):
    for attempt in range(MAX_RETRIES):
        try:
            pt.build_payload(names, timeframe=timeframe)
            return pt.interest_over_time(), None
        except TooManyRequestsError:
            wait = BASE_SLEEP * (2 ** (attempt + 1))
            print(f"    rate-limit, sleeping {wait}s", flush=True)
            time.sleep(wait)
        except Exception as e:
            wait = BASE_SLEEP * (2 ** attempt)
            print(f"    error {type(e).__name__}: {e}; sleeping {wait}s", flush=True)
            time.sleep(wait)
    return None, f"gave up after {MAX_RETRIES} attempts"


def main():
    deaths = pd.read_csv("celebrity-deaths-2010-2025.csv", parse_dates=["date"])
    cohorts = make_cohorts(deaths)
    print(f"{len(deaths)} deaths -> {len(cohorts)} cohorts", flush=True)

    pt = TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=0.5)
    frames, failed = [], []

    for i, cohort in enumerate(cohorts, 1):
        names = [c["name"] for c in cohort]
        earliest = min(c["date"] for c in cohort)
        latest = max(c["date"] for c in cohort)
        start = (earliest - pd.Timedelta(days=PRE_DAYS)).date()
        end = (latest + pd.Timedelta(days=POST_DAYS)).date()
        tf = f"{start} {end}"
        print(f"[{i}/{len(cohorts)}] {tf}  {names}", flush=True)

        df, err = fetch_with_retry(pt, names, tf)
        if err is not None or df is None or df.empty:
            print(f"    FAILED: {err or 'empty response'}", flush=True)
            for c in cohort:
                failed.append({"name": c["name"], "death_date": c["date"].date(),
                               "cohort": i, "error": err or "empty"})
            time.sleep(BASE_SLEEP)
            continue

        df = df.reset_index()
        for c in cohort:
            name, dd = c["name"], c["date"]
            if name not in df.columns:
                failed.append({"name": name, "death_date": dd.date(),
                               "cohort": i, "error": "name absent from response"})
                continue
            sub = df[["date", name]].rename(columns={"date": "view_date", name: "interest"})
            sub["name"] = name
            sub["death_date"] = dd
            sub["days_from_death"] = (sub["view_date"] - dd).dt.days
            sub = sub[(sub["days_from_death"] >= -PRE_DAYS) & (sub["days_from_death"] <= POST_DAYS)]
            sub = sub[["name", "death_date", "view_date", "days_from_death", "interest"]]
            print(f"    {name}: peak={int(sub['interest'].max())}", flush=True)
            frames.append(sub)

        # Periodically flush so a crash mid-run still leaves data on disk.
        if i % 10 == 0 and frames:
            pd.concat(frames, ignore_index=True).to_csv("gtrends_cache.csv", index=False)

        time.sleep(BASE_SLEEP)

    if frames:
        out = pd.concat(frames, ignore_index=True)
        out.to_csv("gtrends_cache.csv", index=False)
        print(f"Wrote {len(out)} rows for {out['name'].nunique()} celebs -> gtrends_cache.csv",
              flush=True)
    if failed:
        pd.DataFrame(failed).to_csv("gtrends_failed.csv", index=False)
        print(f"Wrote {len(failed)} failures -> gtrends_failed.csv", flush=True)


if __name__ == "__main__":
    main()
