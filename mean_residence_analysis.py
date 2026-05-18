# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "pandas",
#     "altair",
#     "scipy",
# ]
# ///

import marimo

__generated_with = "0.23.5"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import pandas as pd
    import altair as alt
    from scipy import stats as scipy_stats

    # The deaths subset is ~5k rows, above Altair's default 5000-row guard.
    alt.data_transformers.disable_max_rows()
    return alt, mo, np, pd, scipy_stats


@app.cell
def _(pd):
    # Full Wikipedia "Deaths in [year]" scrape, 2015-2025, scored with a
    # Wikidata sitelink_count notability proxy. Pageviews were pulled only for
    # the sitelink >= 20 slice, so the notebook focuses on those celebrities.
    scrape = pd.read_csv("deaths_2015_2025_scrape.csv", parse_dates=["date"])
    scrape["age"] = pd.to_numeric(scrape["age"], errors="coerce")
    notable = scrape[scrape["sitelink_count"] >= 20].copy()
    return (notable,)


@app.cell
def _(pd):
    pageviews = pd.read_csv(
        "pageviews_sitelink20.csv",
        parse_dates=["death_date", "view_date"],
    )
    return (pageviews,)


@app.cell
def _(pageviews, pd):
    # Peak (from the death day onwards) plus mean residence time and total
    # excess attention for the post-peak curve, per article. Keyed on
    # wikipedia_title.
    post = pageviews[pageviews["days_from_death"] >= 0].copy()
    pre = pageviews[pageviews["days_from_death"] < 0]

    # Pre-death baseline traffic — the person's "normal" pageviews. Used to
    # isolate the *excess* attention caused by the death.
    baseline_views = pre.groupby("wikipedia_title")["views"].median()
    post = post.merge(
        baseline_views.rename("baseline_views"), on="wikipedia_title", how="left"
    )

    peak_rows = post.loc[post.groupby("wikipedia_title")["views"].idxmax()]
    peaks = peak_rows[
        ["wikipedia_title", "view_date", "days_from_death", "views"]
    ].rename(
        columns={
            "view_date": "peak_date",
            "days_from_death": "peak_days_from_death",
            "views": "peak_views",
        }
    )


    def _mean_residence(group):
        """Post-peak attention metrics for one article.

        - mean_residence_days: centroid (in days since peak) of the EXCESS
          attention curve — how long, on average, the extra attention lingers.
        - total_excess: area under the excess curve — the total surplus
          pageviews the death generated (the *magnitude* of collective
          attention, as opposed to its timing).

        The *_90d variants recompute both over a fixed 90-day post-peak
        window, so they stay comparable across deaths whose pageview history
        was cut short by the edge of the dataset.
        """
        g = group.sort_values("days_from_death").reset_index(drop=True)
        peak_idx = g["views"].idxmax()
        peak_day = g.loc[peak_idx, "days_from_death"]
        after = g.loc[peak_idx:].reset_index(drop=True)

        base = after["baseline_views"].iloc[0]
        if pd.isna(base):
            base = after["views"].min()
        days_since_peak = after["days_from_death"] - peak_day
        excess = (after["views"] - base).clip(lower=0)

        def _centroid_and_area(mask):
            d, e = days_since_peak[mask], excess[mask]
            area = float(e.sum())
            centroid = float((d * e).sum() / area) if area > 0 else pd.NA
            return centroid, area

        mrt, total_excess = _centroid_and_area(days_since_peak >= 0)
        mrt_90, total_excess_90 = _centroid_and_area(days_since_peak <= 90)

        return pd.Series({
            "mean_residence_days": mrt,
            "total_excess": total_excess,
            "mean_residence_days_90d": mrt_90,
            "total_excess_90d": total_excess_90,
            "baseline_views": base,
        })


    decay_stats = (
        post.groupby("wikipedia_title", group_keys=True)
        .apply(_mean_residence, include_groups=False)
        .reset_index()
    )

    pageview_stats = peaks.merge(decay_stats, on="wikipedia_title")
    return (pageview_stats,)


@app.cell
def _(notable, pageview_stats):
    deaths = notable.merge(pageview_stats, on="wikipedia_title", how="left")
    return (deaths,)


@app.cell
def _(alt, deaths):
    chart = (
        alt.Chart(deaths)
        .mark_circle(size=40, opacity=0.4)
        .encode(
            x=alt.X("date:T", title="Date of death"),
            y=alt.Y("age:Q", title="Age at death"),
            tooltip=["name", "description", "date:T", "age", "sitelink_count"],
        )
        .properties(height=420, title="Notable deaths 2015–2025 (sitelink ≥ 20)")
        .interactive()
    )
    chart
    return


@app.cell
def _(pageview_stats):
    pageview_stats
    return


@app.cell
def _(alt, deaths):
    mr_df = deaths.dropna(subset=["mean_residence_days"])

    base_date = alt.Chart(mr_df).encode(
        x=alt.X("date:T", title="Date of death"),
        y=alt.Y("mean_residence_days:Q", title="Mean residence time (days)"),
    )
    scatter_date = base_date.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "peak_views", "mean_residence_days"],
    )
    fit_date = base_date.transform_regression("date", "mean_residence_days").mark_line(color="red")
    # coef[1] is days-per-millisecond; multiply by ms-per-year to get days-per-year.
    annot_date = (
        alt.Chart(mr_df)
        .transform_regression("date", "mean_residence_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1] * 31557600000, ".4f") + " days / year   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    mean_residence_chart = (scatter_date + fit_date + annot_date).properties(
        height=420, title="Mean residence time vs date of death"
    ).interactive()
    mean_residence_chart
    return


@app.cell
def _(mo):
    # Controls for the collective-attention charts below: the time resolution
    # of the buckets, and an optional restriction to a single sitelink-count
    # quartile (Q1 = least notable, Q4 = most notable).
    resolution_dropdown = mo.ui.dropdown(
        options=["Year", "Half-year", "Quarter", "Month"],
        value="Year",
        label="Resolution",
    )
    quartile_dropdown = mo.ui.dropdown(
        options=["All quartiles", "Q1 (least notable)", "Q2", "Q3",
                 "Q4 (most notable)"],
        value="All quartiles",
        label="Sitelink quartile",
    )
    mo.hstack([resolution_dropdown, quartile_dropdown], justify="start", gap=2)
    return quartile_dropdown, resolution_dropdown


@app.cell(hide_code=True)
def _(alt, period_attention, quartile_dropdown, resolution_dropdown):
    # Raw magnitude: how much surplus attention celebrity deaths commanded
    # each period. Mixes the celebrity signal with Wikipedia's own traffic
    # trend. Resolution and the sitelink-quartile filter come from the
    # controls above.
    _order = period_attention["period_label"].tolist()
    _q = quartile_dropdown.value
    collective_attention_chart = (
        alt.Chart(period_attention)
        .mark_bar()
        .encode(
            x=alt.X("period_label:O", sort=_order,
                    title=f"{resolution_dropdown.value} of death"),
            y=alt.Y("total_excess:Q",
                    title="Σ excess pageviews (90-day window)"),
            tooltip=[
                alt.Tooltip("period_label:O", title="Period"),
                alt.Tooltip("total_excess:Q", title="Σ excess", format=",.0f"),
                alt.Tooltip("n_deaths:Q", title="Notable deaths"),
                alt.Tooltip("excess_per_death:Q", title="Excess / death",
                            format=",.0f"),
            ],
        )
        .properties(
            height=360, width=560,
            title="Collective attention on celebrity deaths, by "
                  f"{resolution_dropdown.value.lower()}"
                  + ("" if _q == "All quartiles" else f" — sitelink {_q}"),
        )
    )
    collective_attention_chart
    return


@app.cell
def _(alt, deaths, np, pd):
    # Is the dataset's pool of notable celebrities growing over time? Count
    # notable deaths (sitelink >= 20) per year of death. The scrape ends
    # 2025-09-29, so 2025 is a partial year: it is drawn hollow/grey, kept out
    # of the regression, and its tooltip carries a pro-rated annual estimate.
    # The fit (red) is ordinary least squares over the complete years only;
    # r is Pearson's correlation, R² its square.
    deaths_per_year = (
        deaths.assign(year=deaths["date"].dt.year)
        .groupby("year")
        .size()
        .rename("n_celebrities")
        .reset_index()
    )
    _last = deaths["date"].max()
    _last_full_year = _last.year - 1
    deaths_per_year["complete"] = deaths_per_year["year"] <= _last_full_year
    # Fraction of the calendar year covered (1.0 for complete years); used to
    # pro-rate the partial final year to a comparable full-year estimate.
    _coverage = _last.dayofyear / (
        pd.Timestamp(_last.year, 12, 31).dayofyear
    )
    deaths_per_year["coverage"] = np.where(
        deaths_per_year["complete"], 1.0, _coverage
    )
    deaths_per_year["annualized"] = (
        deaths_per_year["n_celebrities"] / deaths_per_year["coverage"]
    )

    # Ordinary least-squares fit on the complete years only.
    _fit = deaths_per_year[deaths_per_year["complete"]]
    _slope, _intercept = np.polyfit(_fit["year"], _fit["n_celebrities"], 1)
    _r = np.corrcoef(_fit["year"], _fit["n_celebrities"])[0, 1]
    count_trend_label = (
        f"slope = {_slope:+.1f} celebrities / year      "
        f"r = {_r:.3f}      R² = {_r ** 2:.3f}"
    )
    _years = np.array([_fit["year"].min(), _fit["year"].max()])
    count_fit_line = pd.DataFrame({
        "year": _years,
        "n_celebrities": _slope * _years + _intercept,
    })

    _x = alt.X("year:Q", title="Year of death",
               scale=alt.Scale(zero=False), axis=alt.Axis(format="d"))
    _points = (
        alt.Chart(deaths_per_year)
        .mark_circle(size=130)
        .encode(
            x=_x,
            y=alt.Y("n_celebrities:Q", title="Notable celebrity deaths",
                    scale=alt.Scale(zero=False)),
            color=alt.Color(
                "complete:N", title="Complete year",
                scale=alt.Scale(domain=[True, False],
                                range=["#4c78a8", "#bbbbbb"]),
            ),
            tooltip=[
                alt.Tooltip("year:Q", title="Year", format="d"),
                alt.Tooltip("n_celebrities:Q", title="Notable deaths"),
                alt.Tooltip("complete:N", title="Complete year"),
                alt.Tooltip("annualized:Q", title="Annualized estimate",
                            format=",.0f"),
            ],
        )
    )
    _fit_line = (
        alt.Chart(count_fit_line)
        .mark_line(color="red", size=2.5)
        .encode(x=_x, y="n_celebrities:Q")
    )
    _stats = (
        alt.Chart(pd.DataFrame({"label": [count_trend_label]}))
        .mark_text(align="left", baseline="top", x=14, y=12,
                   fontSize=13, fontWeight="bold", color="red")
        .encode(text="label:N")
    )
    celebrity_count_trend = (
        (_points + _fit_line + _stats)
        .properties(
            height=380, width=620,
            title="Are notable celebrity deaths becoming more frequent? "
                  "(OLS fit on complete years only)",
        )
    )
    celebrity_count_trend
    return


@app.cell(hide_code=True)
def _(deaths, pd, quartile_dropdown, resolution_dropdown):
    # Collective attention over time — the size of the celebrity-death
    # "attention economy". Per period of death we sum total_excess_90d (excess
    # pageviews over a fixed 90-day post-peak window) across every celebrity,
    # optionally restricted to one sitelink-count quartile. The fixed window
    # keeps recent periods, whose articles have shorter histories, comparable
    # to older ones. Resolution and quartile are set by the controls above.
    #
    # NOTE: the first and last buckets of the scrape are partial — Wikipedia's
    # daily pageview history starts mid-2015, and the most recent deaths have
    # not been observed for a full 90 days — so treat the endpoints loosely.
    attn = deaths.dropna(subset=["date", "total_excess_90d"]).copy()

    # Sitelink-count quartiles (Q1 = least notable). Ranked percentiles, like
    # the decile view further down, so ties do not collapse the bin edges.
    _pct = attn["sitelink_count"].rank(pct=True, method="first")
    attn["sitelink_quartile"] = pd.cut(
        _pct, [0, 0.25, 0.5, 0.75, 1.0],
        labels=["Q1", "Q2", "Q3", "Q4"], include_lowest=True,
    )
    if quartile_dropdown.value != "All quartiles":
        attn = attn[attn["sitelink_quartile"] == quartile_dropdown.value[:2]]

    # Bucket each death into a period at the chosen resolution. period_start
    # is a sortable datetime; period_label is the human-readable bucket name.
    _res = resolution_dropdown.value
    if _res == "Half-year":
        _half = (attn["date"].dt.month - 1) // 6
        attn["period_start"] = pd.to_datetime(
            dict(year=attn["date"].dt.year, month=_half * 6 + 1, day=1)
        )
        attn["period_label"] = (
            attn["date"].dt.year.astype(str) + " H" + (_half + 1).astype(str)
        )
    else:
        _freq = {"Year": "Y", "Quarter": "Q", "Month": "M"}[_res]
        attn["period_start"] = attn["date"].dt.to_period(_freq).dt.start_time
        if _res == "Year":
            attn["period_label"] = attn["date"].dt.year.astype(str)
        elif _res == "Quarter":
            attn["period_label"] = (
                attn["date"].dt.year.astype(str)
                + " Q" + attn["date"].dt.quarter.astype(str)
            )
        else:  # Month
            attn["period_label"] = attn["date"].dt.strftime("%Y-%m")

    period_attention = (
        attn.groupby(["period_start", "period_label"])
        .agg(
            total_excess=("total_excess_90d", "sum"),
            baseline=("baseline_views", "sum"),
            n_deaths=("total_excess_90d", "size"),
        )
        .reset_index()
        .sort_values("period_start")
    )
    # Σ excess ÷ Σ baseline divides out ambient Wikipedia traffic drift:
    # baseline is the same cohort's "normal" pre-death traffic, so this is
    # excess attention measured in units of the cohort's everyday readership.
    period_attention["excess_per_baseline"] = (
        period_attention["total_excess"] / period_attention["baseline"]
    )
    period_attention["excess_per_death"] = (
        period_attention["total_excess"] / period_attention["n_deaths"]
    )
    period_attention
    return (period_attention,)


@app.cell
def _(alt, period_attention, resolution_dropdown):
    # Same signal with ambient Wikipedia traffic divided out — the closer
    # answer to "is celebrity-as-a-phenomenon itself growing?" Driven by the
    # same resolution / quartile controls as the chart above.
    _order = period_attention["period_label"].tolist()
    collective_attention_normalized = (
        alt.Chart(period_attention)
        .mark_line(point=True, color="#d62728")
        .encode(
            x=alt.X("period_label:O", sort=_order,
                    title=f"{resolution_dropdown.value} of death"),
            y=alt.Y("excess_per_baseline:Q",
                    title="Σ excess ÷ Σ baseline pageviews",
                    scale=alt.Scale(zero=False)),
            tooltip=[
                alt.Tooltip("period_label:O", title="Period"),
                alt.Tooltip("excess_per_baseline:Q",
                            title="Excess / baseline", format=".2f"),
            ],
        )
        .properties(
            height=360, width=560,
            title="Excess attention relative to the cohort's baseline traffic",
        )
    )
    collective_attention_normalized
    return


@app.cell
def _(alt, deaths):
    mr_age_df = deaths.dropna(subset=["mean_residence_days", "age"])

    base_age = alt.Chart(mr_age_df).encode(
        x=alt.X("age:Q", title="Age at death"),
        y=alt.Y("mean_residence_days:Q", title="Mean residence time (days)"),
    )
    scatter_age = base_age.mark_circle(size=40, opacity=0.5).encode(
        tooltip=["name", "description", "date:T", "age", "peak_views", "mean_residence_days"],
    )
    fit_age = base_age.transform_regression("age", "mean_residence_days").mark_line(color="red")
    annot_age = (
        alt.Chart(mr_age_df)
        .transform_regression("age", "mean_residence_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1], ".4f") + " days / year of age   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    mean_residence_vs_age_chart = (scatter_age + fit_age + annot_age).properties(
        height=420, title="Mean residence time vs age at death"
    ).interactive()
    mean_residence_vs_age_chart
    return


@app.cell
def _(alt, deaths, np, pd):
    # Ridge plot: the distribution of mean residence time within each
    # 10-year age-at-death band, stacked as overlapping density ridges.
    ridge_src = deaths.dropna(subset=["mean_residence_days", "age"])
    ridge_src = ridge_src[ridge_src["mean_residence_days"] > 0]

    age_edges = list(range(0, 121, 10))
    age_labels = [f"{lo}–{lo + 10}" for lo in age_edges[:-1]]
    age_group = pd.cut(
        ridge_src["age"], bins=age_edges, labels=age_labels, right=False
    )

    # Shared mean-residence bins so every ridge sits on the same x grid.
    # Capped at the 99th percentile to keep the long tail from squashing it.
    n_bins = 80
    mr_cap = ridge_src["mean_residence_days"].quantile(0.99)
    bin_edges = np.linspace(0, mr_cap, n_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    mr_bin = pd.cut(
        ridge_src["mean_residence_days"].clip(upper=mr_cap),
        bins=bin_edges, labels=bin_centers, include_lowest=True,
    )

    # Count per (age band, mean-residence bin); observed=False fills empty
    # bins with 0 so each ridge is a continuous, gap-free area.
    ridge_counts = (
        pd.DataFrame({"age_group": age_group, "mr_center": mr_bin})
        .dropna()
        .groupby(["age_group", "mr_center"], observed=False)
        .size()
        .rename("count")
        .reset_index()
    )
    ridge_counts["mr_center"] = ridge_counts["mr_center"].astype(float)
    # Drop age bands with no celebrities (e.g. very young deaths).
    present_bands = [
        g for g in age_labels
        if ridge_counts.loc[ridge_counts["age_group"] == g, "count"].sum() > 0
    ]
    ridge_counts = ridge_counts[ridge_counts["age_group"].isin(present_bands)]

    _step = 65        # row height in px
    _overlap = 1.6    # how far adjacent ridges overlap

    mean_residence_ridge = (
        alt.Chart(ridge_counts, height=_step)
        .mark_area(
            interpolate="monotone", fillOpacity=0.75,
            stroke="white", strokeWidth=0.5,
        )
        .encode(
            x=alt.X("mr_center:Q", title="Mean residence time (days)"),
            y=alt.Y(
                "count:Q", axis=None,
                scale=alt.Scale(range=[_step, -_step * _overlap]),
            ),
            fill=alt.Fill(
                "age_group:N", legend=None,
                scale=alt.Scale(scheme="viridis"),
            ),
            row=alt.Row(
                "age_group:N", title="Age at death (years)",
                sort=present_bands,
                header=alt.Header(labelAngle=0, labelAlign="left"),
            ),
        )
        .properties(
            width=620, bounds="flush",
            title="Mean residence time distribution by age-at-death band",
        )
        .configure_facet(spacing=0)
        .configure_view(stroke=None)
        .configure_title(anchor="start")
    )
    mean_residence_ridge
    return


@app.cell
def _(alt, deaths):
    # Mean residence time vs notability (sitelink count).
    mr_sl_df = deaths.dropna(subset=["mean_residence_days", "sitelink_count"])

    base_sl = alt.Chart(mr_sl_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count"),
        y=alt.Y("mean_residence_days:Q", title="Mean residence time (days)"),
    )
    scatter_sl = base_sl.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("date:T", title="Date of death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views", "mean_residence_days"],
    )
    fit_sl = base_sl.transform_regression("sitelink_count", "mean_residence_days").mark_line(color="red")
    annot_sl = (
        alt.Chart(mr_sl_df)
        .transform_regression("sitelink_count", "mean_residence_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1], ".5f") + " days / sitelink   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    mean_residence_vs_sitelink_chart = (scatter_sl + fit_sl + annot_sl).properties(
        height=420, title="Mean residence time vs sitelink count"
    ).interactive()
    mean_residence_vs_sitelink_chart
    return


@app.cell
def _(alt, deaths):
    # Same as above on log-log axes — a power law shows as a straight line here.
    ll_df = deaths.dropna(subset=["mean_residence_days", "sitelink_count"])
    ll_df = ll_df[(ll_df["mean_residence_days"] > 0) & (ll_df["sitelink_count"] > 0)]

    base_ll = alt.Chart(ll_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count",
                scale=alt.Scale(type="log")),
        y=alt.Y("mean_residence_days:Q", title="Mean residence time (days)",
                scale=alt.Scale(type="log")),
    )
    scatter_ll = base_ll.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("date:T", title="Date of death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views", "mean_residence_days"],
    )
    fit_ll = base_ll.transform_regression(
        "sitelink_count", "mean_residence_days", method="pow"
    ).mark_line(color="red")
    annot_ll = (
        alt.Chart(ll_df)
        .transform_regression("sitelink_count", "mean_residence_days", method="pow", params=True)
        .transform_calculate(
            label='"mean residence ≈ " + format(datum.coef[0], ".3f") + " · sitelink^" + format(datum.coef[1], ".3f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    mean_residence_vs_sitelink_loglog_chart = (scatter_ll + fit_ll + annot_ll).properties(
        height=420, title="Mean residence time vs sitelink count (log-log)"
    ).interactive()
    mean_residence_vs_sitelink_loglog_chart
    return


@app.cell
def _(alt, deaths):
    # Notability (sitelink count) vs the size of the death-day spike.
    # peak_views spans several orders of magnitude → log y-axis, power-law fit.
    pv_df = deaths.dropna(subset=["sitelink_count", "peak_views"])
    pv_df = pv_df[pv_df["peak_views"] > 0]

    base_pv = alt.Chart(pv_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count"),
        y=alt.Y("peak_views:Q", title="Peak daily pageviews", scale=alt.Scale(type="log")),
    )
    scatter_pv = base_pv.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views"],
    )
    # Power-law fit: peak_views ≈ a · sitelink_count^b.
    fit_pv = base_pv.transform_regression(
        "sitelink_count", "peak_views", method="pow"
    ).mark_line(color="red")
    annot_pv = (
        alt.Chart(pv_df)
        .transform_regression("sitelink_count", "peak_views", method="pow", params=True)
        .transform_calculate(
            label='"peak ≈ " + format(datum.coef[0], ".0f") + " · sitelink^" + format(datum.coef[1], ".2f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    sitelink_vs_peak_chart = (scatter_pv + fit_pv + annot_pv).properties(
        height=420, title="Peak pageviews vs sitelink count"
    ).interactive()
    sitelink_vs_peak_chart
    return


@app.cell
def _(alt, deaths):
    # Same as above with a log x-axis too — the power-law fit is a straight line here.
    pv_ll_df = deaths.dropna(subset=["sitelink_count", "peak_views"])
    pv_ll_df = pv_ll_df[(pv_ll_df["peak_views"] > 0) & (pv_ll_df["sitelink_count"] > 0)]

    base_pv_ll = alt.Chart(pv_ll_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count",
                scale=alt.Scale(type="log")),
        y=alt.Y("peak_views:Q", title="Peak daily pageviews",
                scale=alt.Scale(type="log")),
    )
    scatter_pv_ll = base_pv_ll.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views"],
    )
    fit_pv_ll = base_pv_ll.transform_regression(
        "sitelink_count", "peak_views", method="pow"
    ).mark_line(color="red")
    annot_pv_ll = (
        alt.Chart(pv_ll_df)
        .transform_regression("sitelink_count", "peak_views", method="pow", params=True)
        .transform_calculate(
            label='"peak ≈ " + format(datum.coef[0], ".0f") + " · sitelink^" + format(datum.coef[1], ".2f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    sitelink_vs_peak_loglog_chart = (scatter_pv_ll + fit_pv_ll + annot_pv_ll).properties(
        height=420, title="Peak pageviews vs sitelink count (log-log)"
    ).interactive()
    sitelink_vs_peak_loglog_chart
    return


@app.cell
def _(alt, deaths):
    # Total excess attention vs notability, linear sitelink axis.
    # total_excess spans several orders of magnitude → log y-axis, power-law
    # fit. The log-log companion below straightens this fit into a line.
    te_df = deaths.dropna(subset=["sitelink_count", "total_excess"])
    te_df = te_df[te_df["total_excess"] > 0]

    base_te = alt.Chart(te_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count"),
        y=alt.Y("total_excess:Q", title="Total excess pageviews",
                scale=alt.Scale(type="log")),
    )
    scatter_te = base_te.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count",
                 "peak_views", "total_excess"],
    )
    # Power-law fit: total_excess ≈ a · sitelink_count^b.
    fit_te = base_te.transform_regression(
        "sitelink_count", "total_excess", method="pow"
    ).mark_line(color="red")
    annot_te = (
        alt.Chart(te_df)
        .transform_regression("sitelink_count", "total_excess", method="pow", params=True)
        .transform_calculate(
            label='"excess ≈ " + format(datum.coef[0], ".1f") + " · sitelink^" + format(datum.coef[1], ".2f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    total_excess_vs_sitelink_chart = (scatter_te + fit_te + annot_te).properties(
        height=420, title="Total excess attention vs sitelink count"
    ).interactive()
    total_excess_vs_sitelink_chart
    return


@app.cell
def _(deaths, mo):
    # Age-at-death filter for the log-log total-excess chart below. Drag the
    # two handles to restrict the scatter — and its power-law fit — to deaths
    # within a chosen age range. Full span = every celebrity (chart unchanged).
    _amin = int(deaths["age"].min())
    _amax = int(deaths["age"].max())
    age_range_slider = mo.ui.range_slider(
        start=_amin, stop=_amax, step=1, value=[_amin, _amax],
        label="Age at death", show_value=True,
    )
    age_range_slider
    return (age_range_slider,)


@app.cell(hide_code=True)
def _(age_range_slider, alt, deaths):
    # Total excess attention vs notability. total_excess is the area under
    # each celebrity's post-peak excess-pageview curve — the *magnitude* of
    # the collective attention their death drew, as opposed to peak_views
    # (the height of the spike) or mean_residence_days (how long it lingers).
    # Both axes span several orders of magnitude, so this is log-log; a power
    # law shows as a straight line. Points colored by age at death, and the
    # whole scatter is restricted to the age range set on the slider above.
    te_ll_full = deaths.dropna(subset=["sitelink_count", "total_excess"])
    te_ll_full = te_ll_full[
        (te_ll_full["total_excess"] > 0) & (te_ll_full["sitelink_count"] > 0)
    ]

    # Pin the axis domains to the FULL dataset, so the log-log scales stay
    # fixed as the age slider narrows the data — every age range is then
    # viewed at the same scale and is directly comparable.
    _x_domain = [
        int(te_ll_full["sitelink_count"].min()),
        int(te_ll_full["sitelink_count"].max()),
    ]
    _y_domain = [
        float(te_ll_full["total_excess"].min()),
        float(te_ll_full["total_excess"].max()),
    ]

    # Restrict to the age-at-death range chosen on the slider above.
    _age_lo, _age_hi = age_range_slider.value
    te_ll_df = te_ll_full[te_ll_full["age"].between(_age_lo, _age_hi)]

    base_te_ll = alt.Chart(te_ll_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count",
                scale=alt.Scale(type="log", domain=_x_domain, clamp=True)),
        y=alt.Y("total_excess:Q", title="Total excess pageviews",
                scale=alt.Scale(type="log", domain=_y_domain, clamp=True)),
    )
    scatter_te_ll = base_te_ll.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count",
                 "peak_views", "total_excess"],
    )
    fit_te_ll = base_te_ll.transform_regression(
        "sitelink_count", "total_excess", method="pow"
    ).mark_line(color="red")
    annot_te_ll = (
        alt.Chart(te_ll_df)
        .transform_regression("sitelink_count", "total_excess", method="pow", params=True)
        .transform_calculate(
            label='"excess ≈ " + format(datum.coef[0], ".1f") + " · sitelink^" + format(datum.coef[1], ".2f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    total_excess_vs_sitelink_loglog_chart = (
        scatter_te_ll + fit_te_ll + annot_te_ll
    ).properties(
        height=420,
        title=f"Total excess attention vs sitelink count (log-log) "
              f"— age {_age_lo}–{_age_hi} (n={len(te_ll_df)})",
    )
    total_excess_vs_sitelink_loglog_chart
    return


@app.cell
def _(alt, deaths, np, pd):
    # Does dying young draw more attention than fame alone explains? Divide
    # notability out of total_excess: regress log10(total_excess) on
    # log10(sitelink_count) and keep the residual — the excess attention a
    # celebrity drew above (+) or below (-) what their sitelink count
    # predicts, in log10 units (residual +1 == 10x the predicted excess).
    # Plotting that residual against age at death isolates the age effect
    # the age slider on the chart above hinted at.
    age_resid_df = deaths.dropna(
        subset=["sitelink_count", "total_excess", "age"]
    ).copy()
    age_resid_df = age_resid_df[
        (age_resid_df["total_excess"] > 0) & (age_resid_df["sitelink_count"] > 0)
    ]

    # Power-law fit on notability alone; the residual is what fame leaves over.
    _lx = np.log10(age_resid_df["sitelink_count"])
    _ly = np.log10(age_resid_df["total_excess"])
    _pl_slope, _pl_int = np.polyfit(_lx, _ly, 1)
    age_resid_df["excess_residual"] = _ly - (_pl_slope * _lx + _pl_int)

    # OLS of the notability-adjusted residual against age at death.
    _a_slope, _a_int = np.polyfit(
        age_resid_df["age"], age_resid_df["excess_residual"], 1
    )
    _a_r = np.corrcoef(age_resid_df["age"], age_resid_df["excess_residual"])[0, 1]
    age_resid_label = (
        f"slope = {_a_slope:+.4f} dex / year of age      "
        f"r = {_a_r:.3f}      R² = {_a_r ** 2:.3f}"
    )
    _span = np.array([age_resid_df["age"].min(), age_resid_df["age"].max()])
    age_resid_fit = pd.DataFrame({
        "age": _span,
        "excess_residual": _a_slope * _span + _a_int,
    })

    _x = alt.X("age:Q", title="Age at death", scale=alt.Scale(zero=False))
    _points = (
        alt.Chart(age_resid_df)
        .mark_circle(size=40, opacity=0.4)
        .encode(
            x=_x,
            y=alt.Y("excess_residual:Q",
                    title="Notability-adjusted excess attention (log₁₀ residual)"),
            color=alt.Color("sitelink_count:Q", title="Sitelink count",
                            scale=alt.Scale(type="log", scheme="viridis")),
            tooltip=["name", "description", "date:T", "age", "sitelink_count",
                     "total_excess",
                     alt.Tooltip("excess_residual:Q", title="Residual (dex)",
                                 format="+.2f")],
        )
    )
    # Residual 0 = exactly the excess notability predicts.
    _zero = (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(strokeDash=[4, 4], color="gray")
        .encode(y="y:Q")
    )
    _fit = (
        alt.Chart(age_resid_fit)
        .mark_line(color="red", size=2.5)
        .encode(x=_x, y="excess_residual:Q")
    )
    _stats = (
        alt.Chart(pd.DataFrame({"label": [age_resid_label]}))
        .mark_text(align="left", baseline="top", x=14, y=12,
                   fontSize=13, fontWeight="bold", color="red")
        .encode(text="label:N")
    )
    excess_residual_vs_age_chart = (
        (_points + _zero + _fit + _stats)
        .properties(
            height=400, width=640,
            title="Notability-adjusted excess attention vs age at death "
                  "— dying young draws extra attention",
        )
        .interactive()
    )
    excess_residual_vs_age_chart
    return (age_resid_df,)


@app.cell(hide_code=True)
def _(age_resid_df, pd):
    # wikidata_bio.csv adds categorical biographical variables - gender,
    # citizenship, occupation and cause of death - keyed on Wikidata QID.
    # Merge them onto the notability-adjusted residual frame so the dropdown
    # chart below can break the residual down by any of them. Citizenship,
    # occupation and cause-of-death cells may hold several pipe-separated
    # values; the chart explodes those where needed.
    bio = pd.read_csv("wikidata_bio.csv")
    resid_bio = age_resid_df.merge(bio, on="qid", how="left")
    return (resid_bio,)


@app.cell
def _(mo):
    # Pick the variable to break the notability-adjusted excess-attention
    # residual down by. "Age at death" reproduces the scatter + OLS fit
    # above; the categorical options switch to a per-category residual box
    # plot.
    x_var_options = {
        "Age at death": "age",
        "Gender": "gender",
        "Citizenship": "citizenship",
        "Occupation": "occupation",
        "Cause of death": "cause_of_death",
    }
    x_var_dropdown = mo.ui.dropdown(
        options=x_var_options, value="Age at death",
        label="Break residual down by",
    )
    x_var_dropdown
    return (x_var_dropdown,)


@app.cell(hide_code=True)
def _(alt, np, pd, resid_bio, x_var_dropdown):
    # Notability-adjusted excess attention broken down by the variable
    # chosen in the dropdown above. Age (numeric) keeps the scatter + OLS
    # fit; the categorical variables become a box plot of the residual per
    # category - multi-valued fields are exploded, categories with fewer
    # than 25 deaths are dropped, and the 15 most common are kept, sorted by
    # median residual. Box colour also tracks the median (red above 0, blue
    # below): which groups punch above what fame alone predicts.
    # Only the columns each chart needs are passed to Altair - the full
    # resid_bio frame inlined as JSON blows past marimo's output size limit.
    _xvar = x_var_dropdown.value
    _xlabel = x_var_dropdown.selected_key
    _y_title = "Notability-adjusted excess attention (log10 residual)"

    if _xvar == "age":
        _scatter_df = resid_bio[["name", "description", "date", "age",
                                 "sitelink_count", "total_excess",
                                 "excess_residual"]]
        _x = alt.X("age:Q", title="Age at death", scale=alt.Scale(zero=False))
        _points = (
            alt.Chart(_scatter_df)
            .mark_circle(size=40, opacity=0.4)
            .encode(
                x=_x,
                y=alt.Y("excess_residual:Q", title=_y_title),
                color=alt.Color("sitelink_count:Q", title="Sitelink count",
                                scale=alt.Scale(type="log", scheme="viridis")),
                tooltip=["name", "description", "date:T", "age", "sitelink_count",
                         "total_excess",
                         alt.Tooltip("excess_residual:Q", title="Residual (dex)",
                                     format="+.2f")],
            )
        )
        _zero = (
            alt.Chart(pd.DataFrame({"y": [0]}))
            .mark_rule(strokeDash=[4, 4], color="gray")
            .encode(y="y:Q")
        )
        _s, _i = np.polyfit(resid_bio["age"], resid_bio["excess_residual"], 1)
        _r = np.corrcoef(resid_bio["age"], resid_bio["excess_residual"])[0, 1]
        _span = np.array([resid_bio["age"].min(), resid_bio["age"].max()])
        _fit = (
            alt.Chart(pd.DataFrame({"age": _span,
                                    "excess_residual": _s * _span + _i}))
            .mark_line(color="red", size=2.5)
            .encode(x=_x, y="excess_residual:Q")
        )
        _stats = (
            alt.Chart(pd.DataFrame({"label": [
                f"slope = {_s:+.4f} dex / year      "
                f"r = {_r:.3f}      R^2 = {_r ** 2:.3f}"]}))
            .mark_text(align="left", baseline="top", x=14, y=12,
                       fontSize=13, fontWeight="bold", color="red")
            .encode(text="label:N")
        )
        x_var_residual_chart = (
            (_points + _zero + _fit + _stats)
            .properties(height=400, width=680,
                        title=f"Notability-adjusted excess attention vs "
                              f"{_xlabel.lower()}")
            .interactive()
        )
    else:
        _cat = resid_bio[["excess_residual", _xvar]].dropna()
        _cat = _cat.assign(**{_xvar: _cat[_xvar].str.split("|")}).explode(_xvar)
        _cat[_xvar] = _cat[_xvar].str.strip()
        _counts = _cat[_xvar].value_counts()
        _keep = _counts[_counts >= 25].head(15)
        _cat = _cat[_cat[_xvar].isin(_keep.index)].copy()
        _cat["category"] = (
            _cat[_xvar] + "  (n=" + _cat[_xvar].map(_keep).astype(str) + ")"
        )
        _order = (
            _cat.groupby("category")["excess_residual"].median()
            .sort_values(ascending=False).index.tolist()
        )
        _zero = (
            alt.Chart(pd.DataFrame({"x": [0]}))
            .mark_rule(strokeDash=[4, 4], color="gray")
            .encode(x="x:Q")
        )
        _box = (
            alt.Chart(_cat[["excess_residual", "category"]])
            .mark_boxplot(size=16, opacity=0.85)
            .encode(
                y=alt.Y("category:N", title=_xlabel, sort=_order),
                x=alt.X("excess_residual:Q", title=_y_title),
                color=alt.Color("median(excess_residual):Q",
                                title="Median residual",
                                scale=alt.Scale(scheme="redblue", domainMid=0)),
            )
        )
        x_var_residual_chart = (
            (_zero + _box)
            .properties(
                height=max(160, len(_order) * 30), width=680,
                title=f"Notability-adjusted excess attention by "
                      f"{_xlabel.lower()}: top {len(_order)} categories, "
                      f"sorted by median residual",
            )
        )

    x_var_residual_chart
    return


@app.cell
def _(alt, deaths):
    age_hist = (
        alt.Chart(deaths.dropna(subset=["age"]))
        .mark_bar()
        .encode(
            x=alt.X("age:Q", bin=alt.Bin(step=5), title="Age at death"),
            y=alt.Y("count():Q", title="Number of celebrities"),
            tooltip=[alt.Tooltip("age:Q", bin=alt.Bin(step=5)), "count():Q"],
        )
        .properties(height=300, width=520, title="Distribution of age at death")
    )
    age_hist
    return


@app.cell
def _(alt, deaths):
    mean_residence_hist = (
        alt.Chart(deaths.dropna(subset=["mean_residence_days"]))
        .mark_bar()
        .encode(
            x=alt.X("mean_residence_days:Q", bin=alt.Bin(maxbins=40),
                    title="Mean residence time (days)"),
            y=alt.Y("count():Q", title="Number of celebrities"),
            tooltip=[alt.Tooltip("mean_residence_days:Q", bin=alt.Bin(maxbins=40)),
                     "count():Q"],
        )
        .properties(height=300, width=520,
                    title="Distribution of mean residence time")
    )
    mean_residence_hist
    return


@app.cell
def _(alt, deaths, np):
    # Same mean-residence distribution as above, but binned on log10.
    # Mean residence time is right-skewed, so log binning spreads the bulk out.
    _mr_log = deaths.dropna(subset=["mean_residence_days"])
    _mr_log = _mr_log[_mr_log["mean_residence_days"] > 0].assign(
        log_mean_residence=lambda d: np.log10(d["mean_residence_days"])
    )

    mean_residence_log_hist = (
        alt.Chart(_mr_log)
        .mark_bar()
        .encode(
            x=alt.X("log_mean_residence:Q", bin=alt.Bin(maxbins=40),
                    title="log₁₀ mean residence time (days)"),
            y=alt.Y("count():Q", title="Number of celebrities"),
            tooltip=[alt.Tooltip("log_mean_residence:Q", bin=alt.Bin(maxbins=40)),
                     "count():Q"],
        )
        .properties(height=300, width=520,
                    title="Distribution of mean residence time (log₁₀)")
    )
    mean_residence_log_hist
    return


@app.cell(hide_code=True)
def _(alt, deaths, mo, np, pd, scipy_stats):
    # Goodness-of-fit test for the mean-residence-time distribution above.
    # Three classic right-skewed families - log-normal, gamma and Weibull -
    # are fit to mean_residence_days by maximum likelihood (location pinned
    # at 0), then ranked three ways: the Kolmogorov-Smirnov statistic D
    # (smaller = closer), its p-value, and AIC (lower = better, penalised
    # for parameter count). With ~5k points the KS p-values are all
    # vanishingly small, so D and AIC are the practical comparison. The
    # fitted PDFs are drawn over a density-normalised histogram, and a Q-Q
    # plot checks the winning fit out into the tail.
    _mr = deaths["mean_residence_days"].dropna()
    _mr = np.sort(_mr[_mr > 0].to_numpy())

    _families = {
        "log-normal": scipy_stats.lognorm,
        "gamma": scipy_stats.gamma,
        "Weibull": scipy_stats.weibull_min,
    }
    _fits = {}
    for _nm, _dist in _families.items():
        _p = _dist.fit(_mr, floc=0)
        _ks = scipy_stats.kstest(_mr, _dist.cdf, args=_p)
        _ll = float(np.sum(_dist.logpdf(_mr, *_p)))
        _aic = 2 * (len(_p) - 1) - 2 * _ll
        _fits[_nm] = {"dist": _dist, "params": _p,
                      "D": _ks.statistic, "p": _ks.pvalue, "aic": _aic}
    _best = min(_fits, key=lambda k: _fits[k]["aic"])

    # Density histogram of the data (40 bins).
    _counts, _edges = np.histogram(_mr, bins=40, density=True)
    _hist_df = pd.DataFrame({
        "bin_start": _edges[:-1],
        "bin_end": _edges[1:],
        "density": _counts,
    })

    # Fitted PDF curves on a shared x grid, long form for colour encoding.
    _grid = np.linspace(float(_mr.min()), float(_mr.max()), 300)
    _pdf_df = pd.concat([
        pd.DataFrame({
            "x": _grid,
            "density": _f["dist"].pdf(_grid, *_f["params"]),
            "family": f"{_n} (D {_f[chr(68)]:.3f}, AIC {_f[chr(97)+chr(105)+chr(99)]:.0f})",
        })
        for _n, _f in _fits.items()
    ], ignore_index=True)

    _hist_layer = (
        alt.Chart(_hist_df)
        .mark_bar(opacity=0.4, color="#5a7fa8")
        .encode(
            x=alt.X("bin_start:Q", title="Mean residence time (days)"),
            x2="bin_end:Q",
            y=alt.Y("density:Q", title="Probability density"),
        )
    )
    _pdf_layer = (
        alt.Chart(_pdf_df)
        .mark_line(size=2.5)
        .encode(
            x="x:Q", y="density:Q",
            color=alt.Color("family:N", title="Fitted distribution",
                            legend=alt.Legend(orient="top", columns=1)),
        )
    )
    _fit_chart = (_hist_layer + _pdf_layer).properties(
        height=320, width=620,
        title=f"Mean residence time vs fitted distributions - best fit: {_best}",
    )

    # Q-Q plot for the winning distribution: sample quantiles against the
    # quantiles that distribution predicts. Points on the dashed line = a
    # perfect fit; drift above the line = the data has a heavier tail.
    _bf = _fits[_best]
    _probs = (np.arange(1, len(_mr) + 1) - 0.5) / len(_mr)
    _theo = _bf["dist"].ppf(_probs, *_bf["params"])
    _qq_df = pd.DataFrame({"theoretical": _theo, "sample": _mr}).iloc[::5]
    _qq_max = float(max(_qq_df["theoretical"].max(), _qq_df["sample"].max()))
    _diag = (
        alt.Chart(pd.DataFrame({"q": [0.0, _qq_max]}))
        .mark_line(color="red", strokeDash=[5, 5])
        .encode(x="q:Q", y="q:Q")
    )
    _qq_layer = (
        alt.Chart(_qq_df)
        .mark_circle(size=16, opacity=0.4, color="#5a7fa8")
        .encode(
            x=alt.X("theoretical:Q", title=f"Theoretical quantiles ({_best})"),
            y=alt.Y("sample:Q", title="Sample quantiles (days)"),
        )
    )
    _qq_chart = (_qq_layer + _diag).properties(
        height=320, width=420, title=f"Q-Q plot - {_best} fit",
    )

    _gof_rows = chr(10).join(
        f"| {_n} | {_f[chr(68)]:.4f} | {_f['p']:.2e} | {_f[chr(97)+chr(105)+chr(99)]:.0f} |"
        for _n, _f in sorted(_fits.items(), key=lambda kv: kv[1]["aic"])
    )
    _gof_md = mo.md(
        "**Goodness of fit** - lower KS *D* and lower AIC both mean a closer "
        "fit." + chr(10) + chr(10) +
        "| Distribution | KS statistic D | KS p-value | AIC |" + chr(10) +
        "|:--|--:|--:|--:|" + chr(10) + _gof_rows + chr(10) + chr(10) +
        f"On this data the **{_best}** distribution wins on both D and AIC."
    )

    mr_distribution_fit = mo.vstack([_gof_md, _fit_chart, _qq_chart])
    mr_distribution_fit
    return


@app.cell(hide_code=True)
def _(alt, deaths, mo, np, pd, scipy_stats):
    # Mean residual life (MRL) - the direct test of memorylessness. For
    # each threshold t, e(t) is the average ADDITIONAL residence time among
    # celebrities who already lingered past t:  e(t) = mean(X - t | X > t).
    # The SHAPE of e(t) reveals the aging behaviour:
    #   flat        -> memoryless (exponential): the past tells you nothing
    #   decreasing  -> "wears out" (rising hazard, gamma with shape k > 1)
    #   increasing  -> heavy tail (log-normal, Pareto)
    # Thresholds are kept only while >= 40 celebrities remain above them so
    # tail noise stays in check. The fitted gamma and log-normal MRL curves
    # are overlaid, plus a flat line at the sample mean - the MRL a truly
    # memoryless (exponential) process would show at every threshold.
    _x = np.sort(deaths["mean_residence_days"].dropna().to_numpy())
    _x = _x[_x > 0]

    _t_grid = np.linspace(float(_x.min()), float(np.quantile(_x, 0.97)), 120)
    _tt, _emrl = [], []
    for _t in _t_grid:
        _surv = _x[_x > _t]
        if len(_surv) >= 40:
            _tt.append(float(_t))
            _emrl.append(float(_surv.mean() - _t))
    _tt = np.array(_tt)

    def _theory_mrl(_dist, _params):
        # e(t) = integral_t^inf S(x) dx / S(t), evaluated numerically.
        _fine = np.linspace(0.0, float(_dist.ppf(0.99999, *_params)), 40000)
        _S = _dist.sf(_fine, *_params)
        _dx = _fine[1] - _fine[0]
        _seg = 0.5 * (_S[:-1] + _S[1:]) * _dx
        _tail = np.concatenate([np.cumsum(_seg[::-1])[::-1], [0.0]])
        _I = np.interp(_tt, _fine, _tail)
        _St = _dist.sf(_tt, *_params)
        return _I / np.where(_St > 0, _St, np.nan)

    _gp = scipy_stats.gamma.fit(_x, floc=0)
    _lp = scipy_stats.lognorm.fit(_x, floc=0)

    _curve_df = pd.concat([
        pd.DataFrame({"t": _tt, "mrl": _theory_mrl(scipy_stats.gamma, _gp),
                      "kind": "gamma fit"}),
        pd.DataFrame({"t": _tt, "mrl": _theory_mrl(scipy_stats.lognorm, _lp),
                      "kind": "log-normal fit"}),
    ], ignore_index=True)
    _flat_df = pd.DataFrame({"t": [_tt[0], _tt[-1]],
                             "mrl": [float(_x.mean())] * 2,
                             "kind": "memoryless (exponential)"})
    _emp_df = pd.DataFrame({"t": _tt, "mrl": _emrl, "kind": "observed data"})

    _palette = {
        "observed data": "#5a7fa8",
        "gamma fit": "#d62728",
        "log-normal fit": "#9467bd",
        "memoryless (exponential)": "#888888",
    }
    _color = alt.Color(
        "kind:N", title="",
        scale=alt.Scale(domain=list(_palette), range=list(_palette.values())),
        legend=alt.Legend(orient="top", columns=2),
    )
    _x_enc = alt.X("t:Q",
                   title="Threshold t - residence time already elapsed (days)")
    _y_enc = alt.Y("mrl:Q", title="Mean residual residence time e(t) (days)",
                   scale=alt.Scale(zero=False))

    _curves = (
        alt.Chart(_curve_df).mark_line(size=2.5)
        .encode(x=_x_enc, y=_y_enc, color=_color)
    )
    _flat = (
        alt.Chart(_flat_df).mark_line(size=2, strokeDash=[6, 4])
        .encode(x=_x_enc, y=_y_enc, color=_color)
    )
    _points = (
        alt.Chart(_emp_df).mark_circle(size=34, opacity=0.75)
        .encode(x=_x_enc, y=_y_enc, color=_color,
                tooltip=[alt.Tooltip("t:Q", title="t (days)", format=".0f"),
                         alt.Tooltip("mrl:Q", title="e(t) (days)", format=".1f")])
    )
    mrl_chart = (
        (_flat + _curves + _points)
        .properties(height=400, width=680,
                    title="Mean residual life - is attention decay memoryless?")
    )

    _mrl_caption = mo.md(
        "The observed e(t) **falls** from about 42 days to roughly 29 as t "
        "grows - it is **not flat**, so attention decay is **not "
        "memoryless**. A celebrity who has already lingered a long time has "
        "*less* expected time remaining, not the same amount: the process "
        "shows aging. The observed decline follows the **gamma** curve "
        "(rising hazard, shape k > 1) down, while the **log-normal** curve "
        "bends upward in the tail, away from the data - the same verdict the "
        "goodness-of-fit test reached one cell up."
    )

    mrl_distribution_test = mo.vstack([mrl_chart, _mrl_caption])
    mrl_distribution_test
    return


@app.cell(hide_code=True)
def _(alt, deaths, mo, np, pd, scipy_stats):
    # Direct test of log-normality. If mean residence time were log-normal,
    # its base-10 log would be exactly normal - a clean symmetric bell. This
    # is a density-normalised histogram of log10(mean_residence_days) with
    # the best-fit normal curve overlaid; the skew of the log values is
    # reported in the title (0 = perfectly log-normal).
    _lr = np.log10(deaths["mean_residence_days"].dropna().to_numpy())
    _lr = _lr[np.isfinite(_lr)]
    _lmu, _lsigma = float(_lr.mean()), float(_lr.std())
    _lskew = float(scipy_stats.skew(_lr))

    _lcounts, _ledges = np.histogram(_lr, bins=40, density=True)
    _lhist_df = pd.DataFrame({"bin_start": _ledges[:-1], "bin_end": _ledges[1:],
                              "density": _lcounts})
    _lgrid = np.linspace(float(_lr.min()), float(_lr.max()), 300)
    _lnorm_df = pd.DataFrame(
        {"x": _lgrid, "density": scipy_stats.norm.pdf(_lgrid, _lmu, _lsigma)})

    _lhist_layer = (
        alt.Chart(_lhist_df).mark_bar(opacity=0.4, color="#5a7fa8")
        .encode(x=alt.X("bin_start:Q",
                        title="log10 mean residence time (days)"),
                x2="bin_end:Q",
                y=alt.Y("density:Q", title="Probability density")))
    _lnorm_layer = (
        alt.Chart(_lnorm_df).mark_line(size=2.5, color="#9467bd")
        .encode(x="x:Q", y="density:Q"))
    lognormality_chart = (_lhist_layer + _lnorm_layer).properties(
        height=320, width=680,
        title=f"Is log(residence time) normal?  skew of log data = {_lskew:+.2f}")

    _lognorm_caption = mo.md(
        f"If the data were log-normal these bars would form a symmetric bell "
        f"hugging the purple normal curve. Instead the log values are clearly "
        f"**left-skewed (skew = {_lskew:+.2f})** - the bulk piles up on the "
        f"right and trails off to the left, undershooting the normal curve on "
        f"its left flank. **Log-normality is rejected**: a true log-normal "
        f"would have skew near 0."
    )
    lognormality_test = mo.vstack([lognormality_chart, _lognorm_caption])
    lognormality_test
    return


@app.cell(hide_code=True)
def _(alt, deaths, mo, np, pd, scipy_stats):
    # Tail-shape test: the survival function S(x) = P(residence > x) drawn
    # on a LOG y-axis against linear x. On these axes an exponential tail is
    # a perfectly straight line, a gamma tail straightens into one, and a
    # log-normal tail keeps curving (it is heavier - it never straightens).
    # The observed survival is shown against all three fitted distributions.
    _xs = np.sort(deaths["mean_residence_days"].dropna().to_numpy())
    _xs = _xs[_xs > 0]
    _ns = len(_xs)
    _Semp = 1.0 - (np.arange(1, _ns + 1) - 0.5) / _ns
    _kept = _Semp >= 1e-3
    _surv_df = pd.DataFrame({"x": _xs[_kept], "S": _Semp[_kept],
                             "kind": "observed data"}).iloc[::6]

    _xmax_s = float(_xs[_kept].max())
    _sgrid = np.linspace(0.5, _xmax_s, 400)
    _ep = scipy_stats.expon.fit(_xs, floc=0)
    _gp2 = scipy_stats.gamma.fit(_xs, floc=0)
    _lp2 = scipy_stats.lognorm.fit(_xs, floc=0)
    _fit_surv = pd.concat([
        pd.DataFrame({"x": _sgrid, "S": scipy_stats.expon.sf(_sgrid, *_ep),
                      "kind": "exponential fit"}),
        pd.DataFrame({"x": _sgrid, "S": scipy_stats.gamma.sf(_sgrid, *_gp2),
                      "kind": "gamma fit"}),
        pd.DataFrame({"x": _sgrid, "S": scipy_stats.lognorm.sf(_sgrid, *_lp2),
                      "kind": "log-normal fit"}),
    ], ignore_index=True)
    _fit_surv = _fit_surv[_fit_surv["S"] >= 5e-4]

    _spalette = {
        "observed data": "#5a7fa8",
        "exponential fit": "#2ca02c",
        "gamma fit": "#d62728",
        "log-normal fit": "#9467bd",
    }
    _scolor = alt.Color(
        "kind:N", title="",
        scale=alt.Scale(domain=list(_spalette), range=list(_spalette.values())),
        legend=alt.Legend(orient="top", columns=2))
    _sx = alt.X("x:Q", title="Residence time x (days)")
    _sy = alt.Y("S:Q", title="Survival  P(residence > x)",
                scale=alt.Scale(type="log"))

    _surv_lines = (alt.Chart(_fit_surv).mark_line(size=2.5)
                   .encode(x=_sx, y=_sy, color=_scolor))
    _surv_pts = (alt.Chart(_surv_df).mark_circle(size=22, opacity=0.6)
                 .encode(x=_sx, y=_sy, color=_scolor,
                         tooltip=[alt.Tooltip("x:Q", title="x (days)", format=".0f"),
                                  alt.Tooltip("S:Q", title="S(x)", format=".4f")]))
    tail_survival_chart = (_surv_lines + _surv_pts).properties(
        height=400, width=680,
        title="Tail shape: survival on a log axis - straight = exponential tail")

    _tail_caption = mo.md(
        "The observed survival curve is close to **straight** on this "
        "log-linear axis - the signature of an **exponential-type (light) "
        "tail**, exactly what a gamma produces. The **gamma** curve tracks "
        "the data through the body and most of the tail. The **exponential** "
        "fit is straight but too shallow - pinned to the overall mean, it "
        "decays too slowly and overstates the tail. The **log-normal** curve "
        "stays high and keeps bending: it predicts far more long-residence "
        "celebrities than the data actually contains. Verdict: a light, "
        "gamma-like tail, not a heavy log-normal one."
    )
    tail_survival_test = mo.vstack([tail_survival_chart, _tail_caption])
    tail_survival_test
    return


@app.cell
def _(deaths, mo, pd):
    # Mean residence time by sitelink-count decile (0–10%, 10–20%, ... 90–100%
    # of the notability distribution). Pick a decile to inspect below.
    q_df = deaths.dropna(subset=["mean_residence_days", "sitelink_count", "date"]).copy()
    pct_rank = q_df["sitelink_count"].rank(pct=True, method="first")
    decile_labels = [f"{i}–{i + 10}%" for i in range(0, 100, 10)]
    q_df["sitelink_decile"] = pd.cut(
        pct_rank,
        bins=[i / 10 for i in range(11)],
        labels=decile_labels,
        include_lowest=True,
    )
    # Numeric year — Vega-Lite's regression transform needs a numeric x.
    q_df["year"] = q_df["date"].dt.year + (q_df["date"].dt.dayofyear - 1) / 365.25

    decile_dropdown = mo.ui.dropdown(
        options=decile_labels,
        value=decile_labels[-1],
        label="Sitelink-count decile",
    )
    decile_dropdown
    return decile_dropdown, q_df


@app.cell(hide_code=True)
def _(alt, decile_dropdown, np, pd, q_df):
    # Scatter of mean residence time vs. year of death for the selected decile,
    # with a least-squares line of best fit (red) and its slope / R² annotated.
    sel_decile = decile_dropdown.value
    decile_df = q_df[q_df["sitelink_decile"] == sel_decile]

    _fit_df = decile_df.dropna(subset=["year", "mean_residence_days"])
    _slope, _intercept = np.polyfit(_fit_df["year"], _fit_df["mean_residence_days"], 1)
    _pred = _slope * _fit_df["year"] + _intercept
    _ss_res = ((_fit_df["mean_residence_days"] - _pred) ** 2).sum()
    _ss_tot = ((_fit_df["mean_residence_days"] - _fit_df["mean_residence_days"].mean()) ** 2).sum()
    _r2 = 1 - _ss_res / _ss_tot
    fit_label = f"slope = {_slope:.3f} days/yr     R² = {_r2:.3f}"

    base_decile = alt.Chart(decile_df).encode(
        x=alt.X("year:Q", title="Year of death",
                scale=alt.Scale(zero=False), axis=alt.Axis(format="d")),
        y=alt.Y("mean_residence_days:Q", title="Mean residence time (days)"),
    )
    points_decile = base_decile.mark_circle(size=60, opacity=0.6).encode(
        color=alt.Color("age:Q", title="Age at death",
                        scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age",
                 "sitelink_count", "peak_views", "mean_residence_days"],
    )
    fit_decile = (
        base_decile
        .transform_regression("year", "mean_residence_days")
        .mark_line(color="red", size=2.5)
    )
    stats_decile = (
        alt.Chart(pd.DataFrame({"label": [fit_label]}))
        .mark_text(align="left", baseline="top", x=14, y=12,
                   fontSize=13, fontWeight="bold", color="red")
        .encode(text="label:N")
    )

    mean_residence_decile_scatter = (
        (points_decile + fit_decile + stats_decile)
        .properties(
            height=420, width=640,
            title=f"Mean residence time vs. year of death — sitelink decile {sel_decile} "
                  f"(n={len(decile_df)})",
        )
        .interactive()
    )
    mean_residence_decile_scatter
    return decile_df, sel_decile


@app.cell(hide_code=True)
def _(alt, decile_df, np, pd, sel_decile):
    # Same decile view as above, but for the death-day pageview spike.
    # peak_views spans orders of magnitude → log y-axis; the fit line,
    # slope and R² are all computed on log10(peak_views).
    pv_decile_df = decile_df.dropna(subset=["year", "peak_views"])
    pv_decile_df = pv_decile_df[pv_decile_df["peak_views"] > 0]

    _log_pv = np.log10(pv_decile_df["peak_views"])
    _pv_slope, _pv_intercept = np.polyfit(pv_decile_df["year"], _log_pv, 1)
    _pv_pred = _pv_slope * pv_decile_df["year"] + _pv_intercept
    _pv_ss_res = ((_log_pv - _pv_pred) ** 2).sum()
    _pv_ss_tot = ((_log_pv - _log_pv.mean()) ** 2).sum()
    _pv_r2 = 1 - _pv_ss_res / _pv_ss_tot
    pv_fit_label = f"slope = {_pv_slope:.3f} log₁₀(views)/yr     R² = {_pv_r2:.3f}"

    # Two-point fit line, mapped back from log space onto the log-scaled axis.
    _pv_years = np.array([pv_decile_df["year"].min(), pv_decile_df["year"].max()])
    pv_fit_line_df = pd.DataFrame({
        "year": _pv_years,
        "peak_views": 10 ** (_pv_slope * _pv_years + _pv_intercept),
    })

    _pv_x = alt.X("year:Q", title="Year of death",
                  scale=alt.Scale(zero=False), axis=alt.Axis(format="d"))
    _pv_y = alt.Y("peak_views:Q", title="Peak daily pageviews",
                  scale=alt.Scale(type="log"))

    points_pv_decile = (
        alt.Chart(pv_decile_df)
        .mark_circle(size=60, opacity=0.6)
        .encode(
            x=_pv_x, y=_pv_y,
            color=alt.Color("age:Q", title="Age at death",
                            scale=alt.Scale(scheme="viridis")),
            tooltip=["name", "description", "date:T", "age",
                     "sitelink_count", "peak_views", "mean_residence_days"],
        )
    )
    fit_pv_decile = (
        alt.Chart(pv_fit_line_df)
        .mark_line(color="red", size=2.5)
        .encode(x=_pv_x, y=_pv_y)
    )
    stats_pv_decile = (
        alt.Chart(pd.DataFrame({"label": [pv_fit_label]}))
        .mark_text(align="left", baseline="top", x=14, y=12,
                   fontSize=13, fontWeight="bold", color="red")
        .encode(text="label:N")
    )

    peak_views_decile_scatter = (
        (points_pv_decile + fit_pv_decile + stats_pv_decile)
        .properties(
            height=420, width=640,
            title=f"Peak pageviews vs. year of death — sitelink decile {sel_decile} "
                  f"(n={len(pv_decile_df)})",
        )
        .interactive()
    )
    peak_views_decile_scatter
    return


@app.cell
def _(alt, deaths):
    # Scatter: mean residence time (log scale) vs. date of death, each celebrity
    # a dot colored by year of birth (year of birth = year of death − age).
    birth_df = deaths.dropna(subset=["age", "date", "mean_residence_days"]).copy()
    birth_df = birth_df[birth_df["mean_residence_days"] > 0]
    birth_df["birth_year"] = birth_df["date"].dt.year - birth_df["age"].astype(int)

    birth_year_scatter = (
        alt.Chart(birth_df)
        .mark_circle(size=40, opacity=0.5)
        .encode(
            x=alt.X("date:T", title="Date of death"),
            y=alt.Y("mean_residence_days:Q",
                    title="Mean residence time (days, log scale)",
                    scale=alt.Scale(type="log")),
            color=alt.Color("birth_year:Q", title="Year of birth",
                            scale=alt.Scale(scheme="viridis")),
            tooltip=["name", "description", "date:T", "birth_year:Q",
                     "age", "sitelink_count", "peak_views", "mean_residence_days"],
        )
        .properties(
            height=380, width=700,
            title="Mean residence time vs. date of death, colored by year of birth",
        )
        .interactive()
    )
    birth_year_scatter
    return


if __name__ == "__main__":
    app.run()
