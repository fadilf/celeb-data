# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "pandas",
#     "altair",
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

    # The deaths subset is ~5k rows, above Altair's default 5000-row guard.
    alt.data_transformers.disable_max_rows()
    return alt, mo, np, pd


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
def _(np, pageviews, pd):
    # Peak (from the death day onwards) plus several "how fast attention
    # fades" metrics, per article. Keyed on wikipedia_title.
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


    def _crossing(after, peak_day, peak_val, frac):
        """Days from peak until views first fall to frac*peak (interpolated)."""
        if peak_val == 0:
            return pd.NA
        thresh = peak_val * frac
        below = after["views"] <= thresh
        if not below.any():
            return pd.NA
        i = below.idxmax()  # first day at-or-below the threshold
        if i == 0:
            return 0.0
        v_prev, v_curr = after.loc[i - 1, "views"], after.loc[i, "views"]
        d_prev, d_curr = after.loc[i - 1, "days_from_death"], after.loc[i, "days_from_death"]
        f = (v_prev - thresh) / (v_prev - v_curr) if v_prev != v_curr else 0.0
        return float(d_prev + f * (d_curr - d_prev) - peak_day)


    def _decay_metrics(group):
        g = group.sort_values("days_from_death").reset_index(drop=True)
        peak_idx = g["views"].idxmax()
        peak_day = g.loc[peak_idx, "days_from_death"]
        peak_val = g.loc[peak_idx, "views"]
        after = g.loc[peak_idx:].reset_index(drop=True)

        # 1. Threshold crossings: time to fall to 1/2 and to 1/10 of peak.
        half = _crossing(after, peak_day, peak_val, 0.5)
        tenth = _crossing(after, peak_day, peak_val, 0.1)

        # 2. Mean residence time: centroid (in days since peak) of the
        #    post-peak EXCESS attention curve. Uses every day, no crossing.
        base = after["baseline_views"].iloc[0]
        if pd.isna(base):
            base = after["views"].min()
        days_since_peak = after["days_from_death"] - peak_day
        excess = (after["views"] - base).clip(lower=0)
        total_excess = excess.sum()
        mrt = (
            float((days_since_peak * excess).sum() / total_excess)
            if total_excess > 0
            else pd.NA
        )

        # 3. Power-law exponent: views ~ (t+1)^(-alpha), fit log-log over the
        #    first 30 post-peak days (before the curve flattens to baseline).
        fit = after[(days_since_peak >= 0) & (days_since_peak <= 30)]
        fit = fit[fit["views"] > 0]
        if len(fit) >= 5:
            t = (fit["days_from_death"] - peak_day).to_numpy()
            slope = np.polyfit(np.log(t + 1), np.log(fit["views"].to_numpy()), 1)[0]
            alpha = float(-slope)
        else:
            alpha = pd.NA

        return pd.Series({
            "half_life_days": half,
            "tenth_life_days": tenth,
            "mean_residence_days": mrt,
            "decay_exponent": alpha,
        })


    decay_stats = (
        post.groupby("wikipedia_title", group_keys=True)
        .apply(_decay_metrics, include_groups=False)
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
    hl_df = deaths.dropna(subset=["half_life_days"])

    base_date = alt.Chart(hl_df).encode(
        x=alt.X("date:T", title="Date of death"),
        y=alt.Y("half_life_days:Q", title="Half-life (days)"),
    )
    scatter_date = base_date.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("age:Q", title="Age at death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "peak_views", "half_life_days"],
    )
    fit_date = base_date.transform_regression("date", "half_life_days").mark_line(color="red")
    # coef[1] is days-per-millisecond; multiply by ms-per-year to get days-per-year.
    annot_date = (
        alt.Chart(hl_df)
        .transform_regression("date", "half_life_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1] * 31557600000, ".4f") + " days / year   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    half_life_chart = (scatter_date + fit_date + annot_date).properties(
        height=420, title="Pageview half-life vs date of death"
    ).interactive()
    half_life_chart
    return


@app.cell
def _(alt, deaths):
    hl_age_df = deaths.dropna(subset=["half_life_days", "age"])

    base_age = alt.Chart(hl_age_df).encode(
        x=alt.X("age:Q", title="Age at death"),
        y=alt.Y("half_life_days:Q", title="Half-life (days)"),
    )
    scatter_age = base_age.mark_circle(size=40, opacity=0.5).encode(
        tooltip=["name", "description", "date:T", "age", "peak_views", "half_life_days"],
    )
    fit_age = base_age.transform_regression("age", "half_life_days").mark_line(color="red")
    annot_age = (
        alt.Chart(hl_age_df)
        .transform_regression("age", "half_life_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1], ".4f") + " days / year of age   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    half_life_vs_age_chart = (scatter_age + fit_age + annot_age).properties(
        height=420, title="Pageview half-life vs age at death"
    ).interactive()
    half_life_vs_age_chart
    return


@app.cell
def _(alt, deaths):
    # Half-life vs notability (sitelink count).
    hl_sl_df = deaths.dropna(subset=["half_life_days", "sitelink_count"])

    base_sl = alt.Chart(hl_sl_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count"),
        y=alt.Y("half_life_days:Q", title="Half-life (days)"),
    )
    scatter_sl = base_sl.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("date:T", title="Date of death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views", "half_life_days"],
    )
    fit_sl = base_sl.transform_regression("sitelink_count", "half_life_days").mark_line(color="red")
    annot_sl = (
        alt.Chart(hl_sl_df)
        .transform_regression("sitelink_count", "half_life_days", params=True)
        .transform_calculate(
            label='"slope = " + format(datum.coef[1], ".5f") + " days / sitelink   R² = " + format(datum.rSquared, ".5f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    half_life_vs_sitelink_chart = (scatter_sl + fit_sl + annot_sl).properties(
        height=420, title="Pageview half-life vs sitelink count"
    ).interactive()
    half_life_vs_sitelink_chart
    return


@app.cell
def _(alt, deaths):
    # Same as above on log-log axes — a power law shows as a straight line here.
    ll_df = deaths.dropna(subset=["half_life_days", "sitelink_count"])
    ll_df = ll_df[(ll_df["half_life_days"] > 0) & (ll_df["sitelink_count"] > 0)]

    base_ll = alt.Chart(ll_df).encode(
        x=alt.X("sitelink_count:Q", title="Wikidata sitelink count",
                scale=alt.Scale(type="log")),
        y=alt.Y("half_life_days:Q", title="Half-life (days)",
                scale=alt.Scale(type="log")),
    )
    scatter_ll = base_ll.mark_circle(size=40, opacity=0.5).encode(
        color=alt.Color("date:T", title="Date of death", scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age", "sitelink_count", "peak_views", "half_life_days"],
    )
    fit_ll = base_ll.transform_regression(
        "sitelink_count", "half_life_days", method="pow"
    ).mark_line(color="red")
    annot_ll = (
        alt.Chart(ll_df)
        .transform_regression("sitelink_count", "half_life_days", method="pow", params=True)
        .transform_calculate(
            label='"half-life ≈ " + format(datum.coef[0], ".3f") + " · sitelink^" + format(datum.coef[1], ".3f") + "   R² = " + format(datum.rSquared, ".3f")'
        )
        .mark_text(align="left", baseline="top", x=8, y=8, color="red", fontSize=12)
        .encode(text=alt.Text("label:N"))
    )
    half_life_vs_sitelink_loglog_chart = (scatter_ll + fit_ll + annot_ll).properties(
        height=420, title="Pageview half-life vs sitelink count (log-log)"
    ).interactive()
    half_life_vs_sitelink_loglog_chart
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
    half_life_hist = (
        alt.Chart(deaths.dropna(subset=["half_life_days"]))
        .mark_bar()
        .encode(
            x=alt.X("half_life_days:Q", bin=alt.Bin(step=0.1), title="Half-life (days)"),
            y=alt.Y("count():Q", title="Number of celebrities"),
            tooltip=[alt.Tooltip("half_life_days:Q", bin=alt.Bin(step=0.1)), "count():Q"],
        )
        .properties(height=300, width=520, title="Distribution of pageview half-life")
    )
    half_life_hist
    return


@app.cell
def _(alt, deaths, np):
    # Same half-life distribution as above, but binned on log10(half-life).
    # Half-life is right-skewed, so log binning spreads the bulk out.
    _hl_log = deaths.dropna(subset=["half_life_days"]).assign(
        log_half_life=lambda d: np.log10(d["half_life_days"])
    )

    half_life_log_hist = (
        alt.Chart(_hl_log)
        .mark_bar()
        .encode(
            x=alt.X("log_half_life:Q", bin=alt.Bin(maxbins=40),
                    title="log₁₀ half-life (days)"),
            y=alt.Y("count():Q", title="Number of celebrities"),
            tooltip=[alt.Tooltip("log_half_life:Q", bin=alt.Bin(maxbins=40)),
                     "count():Q"],
        )
        .properties(height=300, width=520,
                    title="Distribution of pageview half-life (log₁₀)")
    )
    half_life_log_hist
    return


@app.cell
def _(deaths, mo, pd):
    # Half-life by sitelink-count decile (0–10%, 10–20%, ... 90–100%
    # of the notability distribution). Pick a decile to inspect below.
    q_df = deaths.dropna(subset=["half_life_days", "sitelink_count", "date"]).copy()
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
    # Scatter of pageview half-life vs. year of death for the selected decile,
    # with a least-squares line of best fit (red) and its slope / R² annotated.
    sel_decile = decile_dropdown.value
    decile_df = q_df[q_df["sitelink_decile"] == sel_decile]

    _fit_df = decile_df.dropna(subset=["year", "half_life_days"])
    _slope, _intercept = np.polyfit(_fit_df["year"], _fit_df["half_life_days"], 1)
    _pred = _slope * _fit_df["year"] + _intercept
    _ss_res = ((_fit_df["half_life_days"] - _pred) ** 2).sum()
    _ss_tot = ((_fit_df["half_life_days"] - _fit_df["half_life_days"].mean()) ** 2).sum()
    _r2 = 1 - _ss_res / _ss_tot
    fit_label = f"slope = {_slope:.3f} days/yr     R² = {_r2:.3f}"

    base_decile = alt.Chart(decile_df).encode(
        x=alt.X("year:Q", title="Year of death",
                scale=alt.Scale(zero=False), axis=alt.Axis(format="d")),
        y=alt.Y("half_life_days:Q", title="Half-life (days)"),
    )
    points_decile = base_decile.mark_circle(size=60, opacity=0.6).encode(
        color=alt.Color("age:Q", title="Age at death",
                        scale=alt.Scale(scheme="viridis")),
        tooltip=["name", "description", "date:T", "age",
                 "sitelink_count", "peak_views", "half_life_days"],
    )
    fit_decile = (
        base_decile
        .transform_regression("year", "half_life_days")
        .mark_line(color="red", size=2.5)
    )
    stats_decile = (
        alt.Chart(pd.DataFrame({"label": [fit_label]}))
        .mark_text(align="left", baseline="top", x=14, y=12,
                   fontSize=13, fontWeight="bold", color="red")
        .encode(text="label:N")
    )

    halflife_decile_scatter = (
        (points_decile + fit_decile + stats_decile)
        .properties(
            height=420, width=640,
            title=f"Half-life vs. year of death — sitelink decile {sel_decile} "
                  f"(n={len(decile_df)})",
        )
        .interactive()
    )
    halflife_decile_scatter
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
                     "sitelink_count", "peak_views", "half_life_days"],
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
    # Scatter: pageview half-life (log scale) vs. date of death, each celebrity
    # a dot colored by year of birth (year of birth = year of death − age).
    birth_df = deaths.dropna(subset=["age", "date", "half_life_days"]).copy()
    birth_df["birth_year"] = birth_df["date"].dt.year - birth_df["age"].astype(int)

    birth_year_scatter = (
        alt.Chart(birth_df)
        .mark_circle(size=40, opacity=0.5)
        .encode(
            x=alt.X("date:T", title="Date of death"),
            y=alt.Y("half_life_days:Q", title="Half-life (days, log scale)",
                    scale=alt.Scale(type="log")),
            color=alt.Color("birth_year:Q", title="Year of birth",
                            scale=alt.Scale(scheme="viridis")),
            tooltip=["name", "description", "date:T", "birth_year:Q",
                     "age", "sitelink_count", "peak_views", "half_life_days"],
        )
        .properties(
            height=380, width=700,
            title="Half-life vs. date of death, colored by year of birth",
        )
        .interactive()
    )
    birth_year_scatter
    return


@app.cell
def _(alt, deaths):
    # Three resolution-robust alternatives to pageview half-life, compared.
    # Half-life jams 95% of celebrities into [0.5, 2] days because the 50%
    # crossing happens before our second daily sample; these spread out.
    # (Long tails clipped at the cap below so the bulk shape is readable.)
    def _metric_hist(col, title, cap):
        src = deaths[[col]].dropna()
        n_clipped = int((src[col] > cap).sum())
        src = src[src[col] <= cap]
        sub = f"  ({n_clipped} above {cap:g} clipped)" if n_clipped else ""
        return (
            alt.Chart(src)
            .mark_bar()
            .encode(
                x=alt.X(f"{col}:Q", bin=alt.Bin(maxbins=40), title=title),
                y=alt.Y("count():Q", title="Number of celebrities"),
                tooltip=[alt.Tooltip(f"{col}:Q", bin=alt.Bin(maxbins=40)),
                         "count():Q"],
            )
            .properties(height=280, width=260, title=title + sub)
        )

    metric_comparison = alt.hconcat(
        _metric_hist("tenth_life_days", "1/10-life (days)", 15),
        _metric_hist("mean_residence_days", "Mean residence time (days)", 150),
        _metric_hist("decay_exponent", "Power-law exponent α", 3.5),
    ).properties(
        title="How fast people move on — three resolution-robust metrics"
    )
    metric_comparison
    return


@app.cell
def _(alt, deaths):
    # Each celebrity as a point: tail-lingering (mean residence time) vs.
    # initial-decay sharpness (power-law exponent α). x is log-scaled since
    # mean residence time is heavily right-skewed. Spearman ≈ −0.41.
    metric_scatter_df = deaths.dropna(subset=["mean_residence_days", "decay_exponent"])

    mean_residence_vs_alpha = (
        alt.Chart(metric_scatter_df)
        .mark_circle(size=30, opacity=0.4)
        .encode(
            x=alt.X("mean_residence_days:Q",
                    title="Mean residence time (days, log scale)",
                    scale=alt.Scale(type="log")),
            y=alt.Y("decay_exponent:Q", title="Power-law exponent α"),
            tooltip=["name", "description", "mean_residence_days", "decay_exponent",
                     "age", "sitelink_count", "peak_views", "half_life_days"],
        )
        .properties(
            height=440, width=640,
            title="Mean residence time vs. power-law exponent α",
        )
        .interactive()
    )
    mean_residence_vs_alpha
    return


if __name__ == "__main__":
    app.run()
