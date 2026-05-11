# celeb-data

A small dataset for examining how publicly notable celebrity deaths translate into measurable public attention, using Wikipedia pageviews as the attention signal.

The list spans **2010-01-27 through 2025-12-14** and contains **356 notable deaths** — actors, musicians, athletes, authors, political and cultural figures — curated from Variety, Hollywood Reporter, AARP, Britannica, CBS News, ABC News, NPR, and Wikipedia in-memoriam compilations.

For deaths from **2015-07-01 onwards** (the day daily Wikipedia pageviews data begins), this repo also contains daily pageview time series for each celebrity's Wikipedia article in a window of **−90 to +365 days** around the date the death was publicized.

---

## Files

| File | Description |
|---|---|
| `celebrity-deaths-2010-2025.md` | Human-readable list, organized chronologically by year |
| `celebrity-deaths-2010-2025.csv` | Same data as a CSV (356 rows) with Wikipedia article slugs and URLs |
| `pageviews.csv` | Long-format daily pageviews. 124,798 rows × 5 columns covering 277 celebrities (2015-07 onward). Join to the deaths CSV on `name` for the Wikipedia title/URL. |
| `pageviews_log.csv` | One row per fetch attempt with status, date range, and any errors |
| `plots/` | PNG line plots for the celebrities shown below |

---

## CSV schemas

**`celebrity-deaths-2010-2025.csv`**

| Column | Notes |
|---|---|
| `date` | YYYY-MM-DD — date the death was publicized (not necessarily the date of death; see notes) |
| `name` | Display name |
| `description` | Role / claim to fame |
| `wikipedia_title` | Article slug with underscores, ready to pass to the Pageviews API |
| `wikipedia_url` | Full Wikipedia URL (percent-encoded) |
| `note` | Caveats — populated for 5 entries where the date or article isn't strictly biographical |

**`pageviews.csv`**

| Column | Notes |
|---|---|
| `name` | Display name — join key to the deaths CSV for `wikipedia_title` / `wikipedia_url` |
| `death_date` | YYYY-MM-DD |
| `view_date` | YYYY-MM-DD |
| `days_from_death` | Integer; negative is pre-death, 0 is the publicization day, positive is post |
| `views` | Daily pageview count, `agent=user` (bots/spiders excluded) |

---

## Methodology

**Anchor date.** Pageview windows are anchored to the date the death was **made public**, not the (sometimes earlier) date of death. For most celebrities these coincide; for five entries they don't and the CSV's `note` column flags it:

- Kim Jong-il — announced Dec 19, 2011; died Dec 17
- Florian Schneider — announced May 6, 2020; died Apr 21
- Roy Horn — May 8, 2020; article is the duo Siegfried & Roy, not Roy alone
- Akira Toriyama — announced Mar 8, 2024; died Mar 1
- Gene Hackman — body found Feb 26, 2025; estimated death ~Feb 18

**Window.** Each celebrity has up to 456 days of pageview data:
- **−90 days** of pre-death baseline (longer than the typical news-cycle so day-to-day noise smooths out)
- **+365 days** of post-death data (captures the spike, the immediate decay, the long-tail return toward baseline, and any 1-year anniversary bump)

Windows are truncated where they'd run past the 2015-07-01 data floor (a few early 2015 entries) or past today (recent 2025 entries).

**Filter.** `agent=user` excludes crawlers and known bot traffic. `access=all-access` aggregates desktop + mobile-web + mobile-app views.

**Title resolution.** All 356 Wikipedia titles are verified to resolve exactly via the MediaWiki API — no redirects, no missing pages.

---

## Caveats

- **Pre-2015 entries (79 rows) have no daily pageview data.** Daily granularity from the Pageviews API begins 2015-07-01. Pre-2015 deaths are present in the deaths CSV but absent from `pageviews.csv`. The legacy `pagecounts-raw` dumps go back to 2007 but use a different format and methodology.
- **English-Wikipedia bias.** Pageviews are pulled from `en.wikipedia` only. For non-English celebrities (Pelé, Akira Toriyama, Sridevi, Mikhail Gorbachev, Pope Francis, Karl Lagerfeld, Alain Delon, Mario Vargas Llosa, etc.) this under-counts global attention.
- **Selection bias.** The 356-name list is curated toward U.S./U.K. mainstream culture and is not exhaustive. "Notable" is subjective.
- **Article-level vs person-level.** For Roy Horn the article is the duo Siegfried & Roy; pageviews aren't cleanly attributable to one person. Other articles cleanly correspond to a single biography.

---

## Examples

Four illustrative pageview curves, hand-picked for the variety of profiles they show.

### David Bowie (Jan 11, 2016) — the canonical massive spike

![David Bowie pageviews](plots/bowie.png)

Cancer death announced Jan 11, 2016. ~6.95M views the day after — one of the largest single-day pageview events in Wikipedia history. Decay is sharp: views are below 10% of peak within a week.

### Kobe Bryant (Jan 26, 2020) — sudden, sports/cultural shock

![Kobe Bryant pageviews](plots/kobe.png)

Helicopter crash on the day of death itself. Peak of ~9.5M views on the death day (no announcement lag — news broke within minutes). Pre-death baseline is meaningfully non-zero given his ongoing public presence.

### Queen Elizabeth II (Sep 8, 2022) — sustained global event

![Queen Elizabeth II pageviews](plots/qe2.png)

Sustained elevated views for weeks rather than the sharp Bowie-style decay, reflecting the funeral cycle, succession coverage, and tourism around the event.

### Matthew Perry (Oct 28, 2023) — recent death with anniversary bump

![Matthew Perry pageviews](plots/perry.png)

Death-day peak of ~8.8M. The smaller bump visible roughly a year later is the anniversary-of-death revival of interest — a pattern that's visible (though smaller) in many of the celebrities in this dataset once you know to look for it.

---

## Pageview data source

The daily pageviews are pulled from the Wikimedia REST API (`wikimedia.org/api/rest_v1/metrics/pageviews/per-article/...`) — free, no API key required, daily granularity from 2015-07-01 onwards.
