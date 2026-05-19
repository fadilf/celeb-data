# celeb-data

How notable celebrity deaths translate into measurable public attention, using daily Wikipedia pageviews as the attention signal.

Every death recorded on Wikipedia's "Deaths in [year]" pages for **2015-2025** — **98,616 entries** — each scored with a Wikidata `sitelink_count` notability proxy. For the **4,840** most notable (sitelink ≥ 20), daily pageviews are pulled in a **−90 to +365 day** window around the death.

Daily pageview data begins **2015-07-01**, the Wikimedia Pageviews API floor.

---

## Data

| File | Rows | Description |
|---|---|---|
| `deaths_2015_2025_scrape.csv` | 98,616 | All Wikipedia-recorded deaths 2015-2025, with `qid` + `sitelink_count` |
| `wikidata_bio.csv` | 4,840 | Wikidata biography (gender, citizenship, occupation, cause of death) for the sitelink ≥ 20 slice |
| `qid_cache.json` | — | Cache of `wikipedia_title` → Wikidata Q-ID |
| `pageviews_sitelink20.csv` | 2,173,807 | Daily pageviews for the 4,840 sitelink ≥ 20 deaths — **distributed as a [Release asset](https://github.com/fadilf/celeb-data/releases/latest)** (127 MB, over GitHub's file limit) |

### Getting `pageviews_sitelink20.csv`

It is not in the git tree. Download it into the repo root — the notebooks expect it there:

```bash
# with the GitHub CLI
gh release download v1.0 --repo fadilf/celeb-data --pattern pageviews_sitelink20.csv

# or with curl
curl -L -o pageviews_sitelink20.csv \
  https://github.com/fadilf/celeb-data/releases/download/v1.0/pageviews_sitelink20.csv
```

---

## Schemas

**`deaths_2015_2025_scrape.csv`**

| Column | Notes |
|---|---|
| `date` | YYYY-MM-DD date of death |
| `name` | Display name |
| `wikipedia_title` | Article slug (underscores) |
| `age` | Age at death as recorded on Wikipedia's deaths list |
| `description` | Short description from Wikipedia's deaths list |
| `qid` | Wikidata Q-ID (blank for 21 unresolved rows) |
| `sitelink_count` | Number of Wikidata sitelinks — a language-neutral notability proxy |

**`pageviews_sitelink20.csv`**

| Column | Notes |
|---|---|
| `name` | Display name |
| `wikipedia_title` | Article slug — join key to the deaths file |
| `death_date` | YYYY-MM-DD |
| `view_date` | YYYY-MM-DD |
| `days_from_death` | Integer; negative pre-death, 0 the death day, positive post |
| `views` | Daily pageviews, `agent=user` (bots excluded), `access=all-access` |

**`wikidata_bio.csv`** — `qid` joins to the deaths file; `gender`, `citizenship`, `occupation`, `cause_of_death` are pipe-joined when multi-valued. `cause_of_death` is often blank.

---

## Methodology

- **Window.** Each death gets up to 456 days of pageviews: −90 days of pre-death baseline and +365 days of post-death decay (the spike, the long-tail return toward baseline, and any 1-year anniversary bump). Windows are truncated at the 2015-07-01 data floor or the present day.
- **Notability proxy.** Each title resolves to a Wikidata Q-ID (MediaWiki `pageprops`), and the entity's sitelink count is read from Wikidata (`wikibase:sitelinks`) — how many language Wikipedias and sister projects cover it. Cheap to acquire for all 98k rows. Pageviews were pulled at the **≥ 20** cut, roughly the top 5%.

| Threshold | Deaths | Share |
|---|---|---|
| ≥ 5 | 42,947 | 43.6% |
| ≥ 10 | 17,344 | 17.6% |
| ≥ 20 | 5,084 | 5.2% |
| ≥ 50 | 682 | 0.7% |
| ≥ 100 | 78 | 0.1% |

Median is 4; max is 253 (Queen Elizabeth II).

## Caveats

- **English-Wikipedia bias.** Pageviews are from `en.wikipedia` only, under-counting non-English figures. `sitelink_count` does not have this bias.
- **`sitelink_count` measures documented notability, not attention** — a fame proxy. Pageviews are the attention signal.
- **Scrape artifacts.** 21 rows have no `qid`, mostly titles with unrendered MediaWiki template markup that doesn't resolve to Wikidata.

---

## Examples

Four pageview curves illustrating the range of decay profiles.

| | |
|---|---|
| **David Bowie** (Jan 2016) — the canonical massive spike, ~6.95M views the day after, below 10% of peak within a week. | **Kobe Bryant** (Jan 2020) — sudden shock, ~9.5M views on the death day with no announcement lag. |
| ![David Bowie](plots/bowie.png) | ![Kobe Bryant](plots/kobe.png) |
| **Queen Elizabeth II** (Sep 2022) — sustained elevation for weeks through the funeral cycle rather than a sharp decay. | **Matthew Perry** (Oct 2023) — ~8.8M death-day peak, with a visible anniversary bump roughly a year later. |
| ![Queen Elizabeth II](plots/qe2.png) | ![Matthew Perry](plots/perry.png) |

---

## Code

**Pipeline scripts** — standalone [PEP 723](https://peps.python.org/pep-0723/) scripts, run with `uv run <script>.py`. Checkpointed and safe to re-run.

| Script | Does |
|---|---|
| `scrape_deaths.py` | Scrapes Wikipedia "Deaths in [month] [year]" pages → `deaths_2015_2025_scrape.csv` |
| `add_sitelinks.py` | Resolves titles to Wikidata Q-IDs, adds `qid` + `sitelink_count` in place |
| `add_bio.py` | Pulls Wikidata biographical fields for the notable slice → `wikidata_bio.csv` |

**Notebooks** — [marimo](https://marimo.io) notebooks, run with `marimo edit <notebook>.py` (or `uv sync` first). All read `pageviews_sitelink20.csv`, so download the Release asset first.

| Notebook | Focus |
|---|---|
| `notebook.py` | Overview — age, half-life, peak views vs. notability, decay metrics |
| `mean_residence_analysis.py` | Mean residence time of post-peak attention |
| `attention_dwell_time.py` | Attention as a survival curve — how long attention payers dwell |

---

## Data sources

- **Pageviews** — Wikimedia REST API, daily granularity from 2015-07-01.
- **Sitelink counts** — Wikidata Query Service (`wikibase:sitelinks`), titles resolved via the MediaWiki `pageprops` API.
- **Biographical fields** — Wikidata: gender (P21), citizenship (P27), occupation (P106), cause of death (P509).
- **Death lists** — Wikipedia "Deaths in [year]" pages.
