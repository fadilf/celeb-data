# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "pandas",
#     "numpy",
#     "altair",
#     "scipy",
# ]
# ///

import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import pandas as pd
    import altair as alt
    from scipy import stats as scipy_stats

    # Pageview curves run to thousands of points; lift Altair's row guard.
    alt.data_transformers.disable_max_rows()
    return alt, mo, np, pd


@app.cell
def _(mo):
    mo.md(r"""
    # Attention payers — how long do they dwell?

    A different lens on the celebrity-death pageview data.

    Picture, for one celebrity, a crowd of **attention payers**: people
    currently spending time thinking about them, each one a Wikipedia
    pageview. When the page's daily views fall from one day to the next,
    we read that drop as a batch of attention payers *leaving* — and the
    day they left tells us how long they dwelled.

    - Views fall from day 0 to day 1 → that drop-off is the count of
      payers who spent **~0.5 days** thinking about the celebrity.
    - Views fall from day 1 to day 2 → payers who spent **~1.5 days**.
    - …and so on down the decay curve.

    So the decaying pageview curve becomes a **survival curve** for
    attention: the excess views on day *d* are the number of payers
    still paying attention, and the daily drop-offs are the distribution
    of **dwell times**.

    The question this notebook explores, through a series of graphs:

    > **Given that an attention payer has already spent *X* days on a
    > celebrity, how much more time are they expected to spend?**

    If attention were *memoryless*, the answer is a constant — the past
    tells you nothing. If it's *heavy-tailed*, the answer grows with *X*:
    the longer someone has stayed, the longer they'll keep going (a
    Lindy effect). We start with one celebrity and build up.
    """)
    return


@app.cell
def _(pd):
    # Daily Wikipedia pageviews around each celebrity death: one row per
    # (celebrity, calendar day), with days_from_death and the view count.
    # This is the raw material — every drop-off in `views` is a cohort of
    # attention payers leaving.
    pageviews = pd.read_csv(
        "pageviews_sitelink20.csv",
        parse_dates=["death_date", "view_date"],
    )
    return (pageviews,)


@app.cell(hide_code=True)
def _(np, pageviews, pd):
    # attention_curve(title): reframes one celebrity's post-peak pageview
    # decay as a crowd of attention payers leaving.
    #   excess(d) = views(d) - pre-death baseline, clipped at 0
    #             = attention payers still paying attention d days past peak
    #   drop(d)   = excess(d) - excess(d+1)
    #             = payers who left between day d and d+1 (dwell ~ d + 0.5)
    #   eX(d)     = sum over k>=d of excess(k), divided by excess(d)
    #             = expected ADDITIONAL days a payer at day d will spend
    def attention_curve(title):
        g = (pageviews[pageviews["wikipedia_title"] == title]
             .sort_values("days_from_death").reset_index(drop=True))
        baseline = float(g[g["days_from_death"] < 0]["views"].median())
        peak_idx = g["views"].idxmax()
        after = g.loc[peak_idx:].reset_index(drop=True)
        excess = (after["views"] - baseline).clip(lower=0).to_numpy(float)
        day = np.arange(len(excess))
        drop = np.clip(np.append(-np.diff(excess), 0.0), 0.0, None)
        tail_area = np.cumsum(excess[::-1])[::-1]
        eX = tail_area / np.where(excess > 0, excess, np.nan)
        return pd.DataFrame({"day": day, "excess": excess, "drop": drop,
                             "dwell": day + 0.5, "eX": eX})

    return (attention_curve,)


@app.cell(hide_code=True)
def _(attention_curve):
    # Worked example: David Bowie (died 10 Jan 2016) - one of the largest,
    # cleanest spikes in the dataset, so the reframe is easy to see.
    example_title = "David_Bowie"
    example_name = "David Bowie"
    example_curve = attention_curve(example_title)
    return example_curve, example_name


@app.cell(hide_code=True)
def _(np, pageviews):
    # Aggregate across every celebrity. A single pageview curve is one
    # noisy sample; averaging the per-celebrity survival curves over
    # thousands of deaths gives a clean picture. For each celebrity the
    # excess curve is normalised by its peak value, so S(d) runs from 1
    # downward, then averaged day-by-day with every celebrity weighted
    # equally.
    _pv = pageviews
    _base = (_pv[_pv["days_from_death"] < 0]
             .groupby("wikipedia_title")["views"].median())
    _post = _pv[_pv["days_from_death"] >= 0].copy()
    _post["baseline"] = _post["wikipedia_title"].map(_base)
    _post["excess"] = (_post["views"] - _post["baseline"]).clip(lower=0)
    _peak_day = (_post.loc[_post.groupby("wikipedia_title")["views"].idxmax()]
                 .set_index("wikipedia_title")["days_from_death"])
    _post["dsp"] = _post["days_from_death"] - _post["wikipedia_title"].map(_peak_day)
    _post = _post[_post["dsp"] >= 0]
    _e0 = _post[_post["dsp"] == 0].set_index("wikipedia_title")["excess"]
    _post["e0"] = _post["wikipedia_title"].map(_e0)
    _post = _post[_post["e0"] > 0]
    _post["S"] = _post["excess"] / _post["e0"]
    _agg = (_post.groupby("dsp")
            .agg(S=("S", "mean"), n_celebs=("S", "size")).reset_index())
    _Sv = _agg["S"].to_numpy()
    _tail = np.cumsum(_Sv[::-1])[::-1]
    _agg["eX"] = _tail / _Sv
    mean_survival = _agg.rename(columns={"dsp": "day"})
    n_celebrities = int(mean_survival["n_celebs"].iloc[0])
    return mean_survival, n_celebrities


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 1 - One celebrity: the reframe

    Take **David Bowie**. Below, his post-peak pageview decay is read two
    ways: as the count of attention payers still paying attention, and as
    the distribution of how long they each dwelled.
    """)
    return


@app.cell(hide_code=True)
def _(alt, example_curve, example_name):
    # GRAPH 1 - the reframe. Bowie's post-peak excess pageviews read as a
    # survival curve: how many attention payers are still paying attention,
    # day by day. Log y-axis - the crowd shrinks across several orders of
    # magnitude in the first weeks.
    _d1 = example_curve[example_curve["excess"] > 0]
    _area1 = (alt.Chart(_d1).mark_area(opacity=0.25, color="#5a7fa8")
              .encode(x=alt.X("day:Q", title="Days since attention peaked"),
                      y=alt.Y("excess:Q",
                              title="Attention payers still paying (excess pageviews)",
                              scale=alt.Scale(type="log"))))
    _line1 = (alt.Chart(_d1).mark_line(color="#2d5986", size=2)
              .encode(x="day:Q", y="excess:Q",
                      tooltip=[alt.Tooltip("day:Q", title="day"),
                               alt.Tooltip("excess:Q", title="payers still paying",
                                           format=",.0f")]))
    survival_chart = ((_area1 + _line1)
        .properties(height=360, width=680,
                    title=f"{example_name}: a crowd of attention payers, shrinking by the day"))
    survival_chart
    return


@app.cell(hide_code=True)
def _(alt, example_curve, example_name):
    # GRAPH 2 - the dwell-time distribution. Every drop-off in the curve is
    # a cohort of attention payers leaving; this is how many dwelled for
    # each length of time. Log-log axes: a roughly straight line is a power
    # law - a heavy tail, the signature of attention that is NOT memoryless.
    _d2 = example_curve[example_curve["drop"] > 0]
    dwell_chart = (
        alt.Chart(_d2).mark_circle(size=50, opacity=0.6, color="#5a7fa8")
        .encode(
            x=alt.X("dwell:Q", title="Dwell time (days spent on the celebrity)",
                    scale=alt.Scale(type="log")),
            y=alt.Y("drop:Q", title="Attention payers leaving with this dwell time",
                    scale=alt.Scale(type="log")),
            tooltip=[alt.Tooltip("dwell:Q", title="dwell (days)", format=".1f"),
                     alt.Tooltip("drop:Q", title="payers", format=",.0f")])
        .properties(height=360, width=680,
                    title=f"{example_name}: how long did each cohort of payers dwell?"))
    dwell_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 2 - Averaging over every celebrity

    One pageview curve is a noisy sample. Averaging the survival curves of
    all the celebrities in the dataset answers the central question
    cleanly.
    """)
    return


@app.cell(hide_code=True)
def _(alt, mean_survival, mo, n_celebrities, np, pd):
    # GRAPH 3 - the headline. Averaged over thousands of celebrities: given
    # an attention payer has already spent X days, how many MORE days are
    # they expected to spend? A flat line would mean memorylessness - the
    # past carries no information. Instead e(X) climbs steeply: a Lindy
    # effect, where time already spent predicts time still to come.
    _m3 = mean_survival[mean_survival["day"] <= 120]
    _e0v = float(_m3["eX"].iloc[0])
    _fitseg = _m3[_m3["day"] <= 30]
    _slope, _icpt = np.polyfit(_fitseg["day"], _fitseg["eX"], 1)
    _alpha = 2.0 + 1.0 / _slope

    _memoryless = (alt.Chart(pd.DataFrame({"day": [0, 120], "eX": [_e0v, _e0v]}))
        .mark_line(strokeDash=[6, 4], color="#999999", size=2)
        .encode(x="day:Q", y="eX:Q"))
    _eline = (alt.Chart(_m3).mark_line(color="#2d5986", size=2)
        .encode(x="day:Q", y="eX:Q"))
    _epts = (alt.Chart(_m3).mark_circle(size=55, opacity=0.85, color="#2d5986")
        .encode(x=alt.X("day:Q",
                        title="X = days an attention payer has already spent"),
                y=alt.Y("eX:Q", title="e(X) = expected ADDITIONAL days"),
                tooltip=[alt.Tooltip("day:Q", title="X (days)"),
                         alt.Tooltip("eX:Q", title="e(X)", format=".1f")]))
    eX_chart = ((_memoryless + _eline + _epts)
        .properties(height=400, width=680,
                    title="Given X days already spent, how much longer?"))

    _caption = mo.md(
        f"Averaged over **{n_celebrities:,} celebrities**. If attention were "
        f"memoryless, e(X) would sit on the flat grey line at **{_e0v:.1f} "
        f"days** for every X. Instead it climbs from {_e0v:.1f} to over **200 "
        f"days**: a payer who has already lingered two months is expected to "
        f"keep going far longer than one who just arrived. A line fit over "
        f"the first 30 days rises at **{_slope:.1f} extra days per day already "
        f"spent**, implying a power-law dwell-time exponent near **{_alpha:.2f}** "
        f"(a very heavy tail). The plateau past ~2 months is partly the "
        f"365-day observation window, so e(X) at large X is a lower bound."
    )
    eX_test = mo.vstack([eX_chart, _caption])
    eX_test
    return


if __name__ == "__main__":
    app.run()
