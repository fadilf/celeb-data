# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "requests"]
# ///
"""Scrape Wikipedia 'Deaths in <Month> <Year>' pages into a flat CSV.

Each entry is one notable death with a Wikipedia article. Output columns:
date, name, wikipedia_title, age, description. Checkpoints after each year.
"""

import re
import sys
import time
import requests
import pandas as pd

UA = "celeb-data-POC/0.1 (fadilfaizal@gmail.com)"
S = requests.Session()
S.headers["User-Agent"] = UA

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

YEAR_START = 2015
YEAR_END = 2025
OUT = "deaths_2015_2025_scrape.csv"

# * [[Title]] or * [[Title|Display]], age, description
ENTRY = re.compile(r"^\*\s*\[\[([^|\]]+?)(?:\|([^\]]+?))?\]\]\s*,\s*(\d{1,3})\s*,\s*(.+)$")


def get_wikitext(title, max_retries=4):
    for attempt in range(max_retries):
        try:
            r = S.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "prop": "revisions", "titles": title,
                "rvprop": "content", "rvslots": "main",
                "format": "json", "formatversion": "2",
            }, timeout=60)
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            revs = pages[0].get("revisions")
            return revs[0]["slots"]["main"]["content"] if revs else None
        except Exception as e:
            wait = 3 * (2 ** attempt)
            print(f"    retry {attempt+1}/{max_retries}: {type(e).__name__}; sleep {wait}s",
                  file=sys.stderr, flush=True)
            time.sleep(wait)
    return None


def clean_desc(s):
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.DOTALL)
    s = re.sub(r"<ref[^/]*/>", "", s)
    s = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", s)  # [[X|Y]] -> Y
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)             # [[X]]   -> X
    s = re.sub(r"\{\{[^}]*\}\}", "", s)                   # {{tmpl}} ->
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"\s+", " ", s).strip().rstrip(".").strip()
    return s


def parse_month(wt, year, month_num):
    """Collect entries from the first ===DAY=== header until the next
    level-2 section (References / See also / etc.)."""
    rows, skipped = [], 0
    current_day = None
    started = False
    for line in wt.split("\n"):
        day_h = re.match(r"^===\s*(\d{1,2})\s*===\s*$", line)
        if day_h:
            current_day = int(day_h.group(1))
            started = True
            continue
        if started and re.match(r"^==[^=]", line):
            break  # day list finished
        if current_day is None:
            continue
        m = ENTRY.match(line)
        if not m:
            if line.lstrip().startswith("*"):
                skipped += 1
            continue
        wp_title, display, age, rest = m.groups()
        try:
            date = pd.Timestamp(year, month_num, current_day)
        except ValueError:
            skipped += 1
            continue
        rows.append({
            "date": date,
            "name": (display or wp_title).strip(),
            "wikipedia_title": wp_title.strip().replace(" ", "_"),
            "age": int(age),
            "description": clean_desc(rest),
        })
    return rows, skipped


def main():
    all_rows, total_skipped = [], 0
    for year in range(YEAR_START, YEAR_END + 1):
        for mi, month in enumerate(MONTHS, 1):
            title = f"Deaths in {month} {year}"
            wt = get_wikitext(title)
            if wt is None:
                print(f"  {title}: MISSING/FAILED", flush=True)
                continue
            rows, skipped = parse_month(wt, year, mi)
            all_rows.extend(rows)
            total_skipped += skipped
            print(f"  {title}: {len(rows)} entries ({skipped} skipped)", flush=True)
            time.sleep(1)
        pd.DataFrame(all_rows).to_csv(OUT, index=False)
        print(f"-- {year} done | {len(all_rows)} cumulative | checkpoint saved", flush=True)

    df = pd.DataFrame(all_rows)
    df.to_csv(OUT, index=False)
    print(f"TOTAL: {len(df)} entries, {total_skipped} bullet lines skipped -> {OUT}",
          flush=True)


if __name__ == "__main__":
    main()
