# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "requests"]
# ///
"""Pull biographical fields from Wikidata for the sitelink>=20 celebrities.

For each Wikidata QID, fetches gender (P21), country of citizenship (P27),
occupation (P106) and cause of death (P509) via batched SPARQL. Multi-valued
fields are pipe-joined. Output: wikidata_bio.csv keyed by qid.
"""

import os
import sys
import time
import requests
import pandas as pd

UA = "celeb-data-POC/0.1 (fadilfaizal@gmail.com)"
S = requests.Session()
S.headers["User-Agent"] = UA

BATCH = 100          # smaller batches — WDQS has been flaky
OUT = "wikidata_bio.csv"

QUERY_TMPL = """
SELECT ?item
  (GROUP_CONCAT(DISTINCT ?genderL; separator="|") AS ?gender)
  (GROUP_CONCAT(DISTINCT ?citizenshipL; separator="|") AS ?citizenship)
  (GROUP_CONCAT(DISTINCT ?occupationL; separator="|") AS ?occupation)
  (GROUP_CONCAT(DISTINCT ?codL; separator="|") AS ?cause_of_death)
WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P21 ?g. ?g rdfs:label ?genderL. FILTER(LANG(?genderL)="en") }
  OPTIONAL { ?item wdt:P27 ?c. ?c rdfs:label ?citizenshipL. FILTER(LANG(?citizenshipL)="en") }
  OPTIONAL { ?item wdt:P106 ?o. ?o rdfs:label ?occupationL. FILTER(LANG(?occupationL)="en") }
  OPTIONAL { ?item wdt:P509 ?d. ?d rdfs:label ?codL. FILTER(LANG(?codL)="en") }
}
GROUP BY ?item
"""


def sparql(query, max_retries=6):
    for attempt in range(max_retries):
        try:
            r = S.post("https://query.wikidata.org/sparql",
                       data={"query": query, "format": "json"},
                       headers={"Accept": "application/sparql-results+json"},
                       timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = 3 * (2 ** attempt)
            print(f"    retry {attempt+1}/{max_retries}: {type(e).__name__}; sleep {wait}s",
                  file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError("max retries exceeded")


def main():
    df = pd.read_csv("deaths_2015_2025_scrape.csv")
    notable = df[df["sitelink_count"] >= 20]
    qids = sorted(notable["qid"].dropna().unique())

    # Resume: keep rows already fetched, only query the missing QIDs.
    rows = []
    done = set()
    if os.path.exists(OUT):
        prev = pd.read_csv(OUT)
        rows = prev.to_dict("records")
        done = set(prev["qid"])
    qids = [q for q in qids if q not in done]
    print(f"{len(notable)} notable rows | {len(done)} already done | "
          f"{len(qids)} QIDs to fetch", flush=True)

    n_batches = (len(qids) + BATCH - 1) // BATCH
    for i in range(0, len(qids), BATCH):
        batch = qids[i:i+BATCH]
        values = " ".join(f"wd:{q}" for q in batch)
        data = sparql(QUERY_TMPL % values)
        for b in data["results"]["bindings"]:
            rows.append({
                "qid": b["item"]["value"].rsplit("/", 1)[-1],
                "gender": b.get("gender", {}).get("value", ""),
                "citizenship": b.get("citizenship", {}).get("value", ""),
                "occupation": b.get("occupation", {}).get("value", ""),
                "cause_of_death": b.get("cause_of_death", {}).get("value", ""),
            })
        pd.DataFrame(rows).to_csv(OUT, index=False)  # checkpoint
        print(f"  SPARQL {i//BATCH+1}/{n_batches}: {len(batch)} ids "
              f"(cumulative {len(rows)})", flush=True)
        time.sleep(2)

    bio = pd.DataFrame(rows)
    bio.to_csv(OUT, index=False)
    print(f"Saved {len(bio)} rows -> {OUT}", flush=True)

    print()
    for col in ["gender", "citizenship", "occupation", "cause_of_death"]:
        filled = (bio[col].fillna("").astype(str).str.len() > 0).sum()
        print(f"  {col}: {filled}/{len(bio)} populated ({100*filled/len(bio):.0f}%)")
    print()
    print("Gender breakdown:", bio["gender"].value_counts().head(5).to_dict())
    print()
    cod = bio["cause_of_death"].fillna("").astype(str)
    cod = cod[cod.str.len() > 0]
    print(f"Cause of death present for {len(cod)} celebs. Top values:")
    print(cod.value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
