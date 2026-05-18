# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "requests"]
# ///
"""Add qid and sitelink_count columns to deaths_2015_2025_scrape.csv (in place).

Two checkpointed stages:
  1. MediaWiki pageprops -> Q-ID per title (50 titles/call). Saves qid_cache.json.
  2. Wikidata SPARQL -> sitelink count per Q-ID (300 Q-IDs/POST query).
The qid_cache.json is reused on re-runs so a SPARQL failure doesn't waste
the slower pageprops stage.
"""

import json
import os
import sys
import time
import requests
import pandas as pd

UA = "celeb-data-POC/0.1 (fadilfaizal@gmail.com)"
QID_CACHE = "qid_cache.json"
S = requests.Session()
S.headers["User-Agent"] = UA


def get_json(url, params=None, data=None, method="GET",
             max_retries=4, sleep_base=3, headers=None):
    for attempt in range(max_retries):
        try:
            if method == "GET":
                r = S.get(url, params=params, timeout=60, headers=headers)
            else:
                r = S.post(url, data=data, timeout=120, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = sleep_base * (2 ** attempt)
            print(f"    retry {attempt+1}/{max_retries}: {type(e).__name__}; sleep {wait}s",
                  file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError("max retries exceeded")


def resolve_qids(titles):
    if os.path.exists(QID_CACHE):
        with open(QID_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
        print(f"loaded {len(cached)} Q-IDs from cache", flush=True)
        return cached
    title_to_qid = {}
    n_batches = (len(titles) + 49) // 50
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        data = get_json("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
            "titles": "|".join(t.replace("_", " ") for t in batch),
            "format": "json", "formatversion": "2", "redirects": "1",
        })
        redirects = {r["from"]: r["to"] for r in data["query"].get("redirects", [])}
        normalized = {n["from"]: n["to"] for n in data["query"].get("normalized", [])}
        page_by_title = {p["title"]: p for p in data["query"]["pages"]}
        for orig in batch:
            spaced = orig.replace("_", " ")
            norm = normalized.get(spaced, spaced)
            target = redirects.get(norm, norm)
            page = page_by_title.get(target)
            qid = page and page.get("pageprops", {}).get("wikibase_item")
            if qid:
                title_to_qid[orig] = qid
        if (i // 50) % 10 == 0:
            print(f"  pageprops {i//50+1}/{n_batches} (resolved: {len(title_to_qid)})",
                  flush=True)
        time.sleep(0.6)
    with open(QID_CACHE, "w", encoding="utf-8") as f:
        json.dump(title_to_qid, f)
    print(f"resolved {len(title_to_qid)}/{len(titles)}, cached -> {QID_CACHE}", flush=True)
    return title_to_qid


def get_sitelink_counts(qids):
    qid_to_count = {}
    batch_size = 300
    n_batches = (len(qids) + batch_size - 1) // batch_size
    for i in range(0, len(qids), batch_size):
        batch = qids[i:i+batch_size]
        values = " ".join(f"wd:{q}" for q in batch)
        query = (
            "SELECT ?item ?c WHERE { "
            f"VALUES ?item {{ {values} }} "
            "?item wikibase:sitelinks ?c . "
            "}"
        )
        data = get_json(
            "https://query.wikidata.org/sparql",
            method="POST",
            data={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        for b in data["results"]["bindings"]:
            q = b["item"]["value"].rsplit("/", 1)[-1]
            qid_to_count[q] = int(b["c"]["value"])
        print(f"  SPARQL {i//batch_size+1}/{n_batches}: {len(batch)} ids "
              f"(cumulative: {len(qid_to_count)})", flush=True)
        time.sleep(2)
    return qid_to_count


SCRAPE_CSV = "deaths_2015_2025_scrape.csv"


def main():
    df = pd.read_csv(SCRAPE_CSV)
    titles = df["wikipedia_title"].unique().tolist()
    print(f"{len(df)} entries, {len(titles)} unique titles", flush=True)

    title_to_qid = resolve_qids(titles)
    qids = list(set(title_to_qid.values()))
    qid_to_count = get_sitelink_counts(qids)

    df["qid"] = df["wikipedia_title"].map(title_to_qid)
    df["sitelink_count"] = df["qid"].map(qid_to_count)
    df.to_csv(SCRAPE_CSV, index=False)
    print(f"Saved {len(df)} rows -> {SCRAPE_CSV}", flush=True)

    print()
    print("sitelink_count distribution:")
    print(df["sitelink_count"].describe().round(1))
    print()
    print("Threshold sweep:")
    for cutoff in [1, 3, 5, 10, 15, 20, 30, 50, 100, 150]:
        n = (df["sitelink_count"] >= cutoff).sum()
        print(f"  sitelink_count >= {cutoff:>3}: {n:>5} ({100*n/len(df):>4.1f}%)")
    print()
    print("Top 15 by sitelink_count:")
    cols = ["date", "name", "age", "sitelink_count", "description"]
    print(df.nlargest(15, "sitelink_count")[cols].to_string(index=False))


if __name__ == "__main__":
    main()
