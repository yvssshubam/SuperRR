"""Step 6: figures for the README.
Usage (after steps 01-05 and the experiments that feed it):
    python -I 06_figures.py <out_dir> [fig_dir]
Reads only files the pipeline and experiments write to <out_dir>; writes PNGs to fig_dir (default: figures/).
Figures that need an experiment output are skipped with a note if that file is missing:
  readiness_test.csv  <- experiments/readiness_test.py
  additions_test.csv  <- experiments/additions_test.py
  spin_edge_test.csv  <- experiments/spin_edge_test.py
"""
import os, sys, json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

OUT = sys.argv[1]
FIG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(FIG, exist_ok=True)

# ---------- style: validated two-slot categorical palette (blue, orange) + quiet greys ----------
BLUE, ORANGE = "#2a78d6", "#eb6834"          # categorical slots 1-2 (validated: CVD dE 24.7, normal dE 33.6)
GREY, GREY_D = "#b4b2ab", "#8a8880"           # quiet data / reference marks
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e7e6e2", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "legend.frameon": False, "axes.titlelocation": "left",
})

def frame(fig, title, subtitle, source):
    fig.text(0.012, 0.975, title, ha="left", va="top", fontsize=13.5, fontweight="bold", color=INK)
    fig.text(0.012, 0.925, subtitle, ha="left", va="top", fontsize=10, color=INK2)
    fig.text(0.012, 0.012, source, ha="left", va="bottom", fontsize=8, color=INK2)

def hgrid(ax, axis="y"):
    ax.grid(True, axis=axis, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax.tick_params(length=0)

def save(fig, name):
    p = os.path.join(FIG, name); fig.savefig(p, dpi=160); plt.close(fig); print("wrote", p)

def have(f):
    ok = os.path.exists(os.path.join(OUT, f))
    if not ok: print(f"skipped: {f} not found in {OUT} (run the experiment that writes it)")
    return ok

b = pd.read_pickle(f"{OUT}/balls_scored.pkl")
fin = {(rt, r): pd.read_csv(f"{OUT}/{r}{'' if rt == 'readiness' else '_career'}_final.csv", index_col=0)
       for rt in ["readiness", "career"] for r in ["bat", "bowl"]}
short = lambda n: n.replace("Namboori Tilak Varma", "Tilak Varma")

# ---------- 1. win-probability calibration ----------
b["won"] = (b.win_team_id == b.batting_team_id).astype(float)
fig, ax = plt.subplots(figsize=(7.6, 5.0)); fig.subplots_adjust(left=0.1, right=0.96, top=0.8, bottom=0.14)
ax.plot([0, 1], [0, 1], color=GREY, linewidth=1.2, zorder=1, label="Perfect calibration")
gaps = []
for inn, col, lab in [(1, ORANGE, "Setting a total"), (2, BLUE, "Chasing")]:
    d = b[b.innings == inn]; band = pd.cut(d.wp_before, np.linspace(0, 1, 11), include_lowest=True)
    g = d.groupby(band, observed=True).agg(pred=("wp_before", "mean"), act=("won", "mean"), n=("won", "size"))
    gaps.append((g.act - g.pred).abs().max())
    ax.plot(g.pred, g.act, color=col, linewidth=2, marker="o", markersize=6, markeredgecolor=SURF, markeredgewidth=1.5, label=lab, zorder=3)
ax.set_xlim(0, 1); ax.set_ylim(0, 1); hgrid(ax, "both")
ax.set_xlabel("Predicted win probability (mean of each 10% band)"); ax.set_ylabel("Actual win rate")
ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0)); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
ax.legend(loc="upper left", fontsize=9.5, labelcolor=INK)
frame(fig, f"Predicted and actual win rates agree within {100 * max(gaps):.0f} points in every band",
      "Win-probability model (Markov + Platt calibration with Elo), every ball of 788 matches",
      "Source: 02_pressure.py, out/balls_scored.pkl")
save(fig, "fig01_wp_calibration.png")

# ---------- 2. leverage vs conventional formula ----------
v = json.load(open(f"{OUT}/validation.json")); val = v["validation"]
sw = {r["pressure"]: r["abs_wpa"] for r in v["behaviour"]}; swc = {r["alt_pressure"]: r["abs_wpa"] for r in v["abs_wpa_conventional"]}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.2, 4.4), gridspec_kw=dict(width_ratios=[1, 1.15], wspace=0.75))
fig.subplots_adjust(left=0.17, right=0.97, top=0.76, bottom=0.14)
lab = ["Leverage Index", "Conventional formula"]; vals = [val["leverage_share_wp_below_10"], val["conventional_share_wp_below_10"]]
a1.barh([1, 0], vals, color=[BLUE, GREY], height=0.5)
for y, x in zip([1, 0], vals): a1.text(x + 0.015, y, f"{100 * x:.0f}%", va="center", fontsize=11, fontweight="bold", color=INK)
a1.set_yticks([1, 0], lab); a1.set_xlim(0, 0.85); a1.set_xticks([]); a1.spines["bottom"].set_visible(False); a1.tick_params(length=0)
a1.set_title("Flagged chase balls where the chase\nwas already lost (win chance < 10%)", fontsize=9.5, color=INK2, pad=8)
for i, (s, t) in enumerate([(sw, "Leverage Index"), (swc, "Conventional formula")]):
    y = 1 - i
    a2.barh(y + 0.15, s[True], height=0.28, color=BLUE if i == 0 else GREY)
    a2.barh(y - 0.15, s[False], height=0.28, color="#dcdad4")
    a2.text(s[True] + 0.04, y + 0.15, f"{s[True]:.2f} pressure balls", va="center", fontsize=9, color=INK)
    a2.text(s[False] + 0.04, y - 0.15, f"{s[False]:.2f} other balls", va="center", fontsize=9, color=INK2)
    a2.text(3.55, y, f"{s[True] / s[False]:.1f}x", va="center", ha="right", fontsize=12, fontweight="bold", color=INK)
a2.set_yticks([1, 0], lab); a2.set_xlim(0, 3.6); a2.set_xticks([]); a2.spines["bottom"].set_visible(False); a2.tick_params(length=0)
a2.set_title("Average win-probability swing per ball\n(percentage points)", fontsize=9.5, color=INK2, pad=8)
frame(fig, "Leverage flags the balls that decide matches; a formula flags lost causes",
      "Leverage Index vs a required-rate x wickets x stage formula, top 25% of balls flagged by each",
      "Source: 04_robustness.py, out/validation.json")
save(fig, "fig02_leverage_vs_conventional.png")

# ---------- 3. leverage by over ----------
fig, ax = plt.subplots(figsize=(8.4, 4.4)); fig.subplots_adjust(left=0.08, right=0.85, top=0.78, bottom=0.14)
ax.axvspan(0.5, 6.5, color=GRID, alpha=0.45, linewidth=0); ax.axvspan(15.5, 20.5, color=GRID, alpha=0.45, linewidth=0)
for xm, t in [(3.5, "Powerplay"), (11, "Middle overs"), (18, "Death")]: ax.text(xm, 0.02, t, transform=ax.get_xaxis_transform(), ha="center", fontsize=8.5, color=INK2)
for inn, col, lab in [(1, ORANGE, "Setting a total"), (2, BLUE, "Chasing")]:
    g = b[b.innings == inn].groupby("over").li.mean()
    ax.plot(g.index, g.values, color=col, linewidth=2, marker="o", markersize=4.5)
    ax.text(20.4, g.iloc[-1], f"{lab}  {g.iloc[-1]:.1f}", va="center", fontsize=9.5, color=INK)
ax.axhline(1, color=GREY_D, linewidth=1); ax.text(7, 1.05, "average ball = 1.0", fontsize=8.5, color=INK2)
ax.set_xlim(0.5, 20.5); ax.set_xticks(range(1, 21)); ax.set_ylim(0, None); hgrid(ax)
ax.set_xlabel("Over"); ax.set_ylabel("Mean Leverage Index")
peak = b[b.innings == 2].groupby("over").li.mean()
frame(fig, f"Pressure peaks at the death of a chase: {peak.max():.1f}x an average ball in over {peak.idxmax()}",
      "Mean Leverage Index by over (how much the result can swing on a ball; 1.0 = average)",
      "Source: 02_pressure.py, out/balls_scored.pkl")
save(fig, "fig03_leverage_by_over.png")

# ---------- 4. top-10 normal vs pressure (conventional stats) ----------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.4, 5.4), gridspec_kw=dict(wspace=0.75))
fig.subplots_adjust(left=0.17, right=0.95, top=0.74, bottom=0.12)
for ax, r, cn, cp, unit, better in [(a1, "bat", "SR_N", "SR_P", "Strike rate", "higher"), (a2, "bowl", "econ_N", "econ_P", "Economy (runs per over)", "lower")]:
    e = fin[("readiness", r)].head(10); ys = np.arange(10)[::-1]
    for y, (_, x) in zip(ys, e.iterrows()):
        ax.plot([x[cn], x[cp]], [y, y], color=GRID, linewidth=2.5, zorder=1)
        ax.scatter(x[cn], y, s=46, color=GREY, zorder=2, edgecolor=SURF, linewidth=1.5)
        ax.scatter(x[cp], y, s=58, color=BLUE, zorder=3, edgecolor=SURF, linewidth=1.5)
        ax.text(x[cp], y + 0.32, f"{x[cp]:.0f}" if r == "bat" else f"{x[cp]:.1f}", fontsize=8.5, color=INK, ha="center")
    ax.set_yticks(ys, [f"{i}. {short(n)}" for i, n in enumerate(e.name, 1)], fontsize=9); hgrid(ax, "x")
    ax.set_xlabel(f"{unit} ({better} is better)")
    nb = int((e[cp] > e[cn]).sum()) if r == "bat" else int((e[cp] < e[cn]).sum())
    ax.set_title(f"{'Batters' if r == 'bat' else 'Bowlers'}: {nb} of 10 {'score faster' if r == 'bat' else 'concede less'}\nunder pressure", fontsize=10, color=INK, fontweight="bold", pad=10)
frame(fig, "The submitted top 10 under pressure vs in normal situations",
      "Readiness top 10: pressure balls (blue dot) vs normal balls (grey dot), 2022-2026. Pressure balls are mostly death overs,\nwhere every bowler concedes more; the ranking compares each ball with the average player in the same situation, not these raw stats.",
      "Source: 03_ratings.py, out/bat_final.csv and out/bowl_final.csv")
save(fig, "fig04_top10_normal_vs_pressure.png")

# ---------- 5. bootstrap rank ranges ----------
fig, axs = plt.subplots(1, 2, figsize=(10.4, 5.4), gridspec_kw=dict(wspace=0.75))
fig.subplots_adjust(left=0.17, right=0.93, top=0.8, bottom=0.12)
for ax, r in zip(axs, ["bat", "bowl"]):
    e = fin[("readiness", r)].head(10); ys = np.arange(10)[::-1]
    ax.axvspan(0.5, 10.5, color=BLUE, alpha=0.06, linewidth=0)
    for y, (_, x) in zip(ys, e.iterrows()):
        c = BLUE if x.top10_freq >= 0.7 else GREY_D
        ax.plot([x.rank_p10, x.rank_p90], [y, y], color=c, linewidth=2, solid_capstyle="round")
        ax.scatter(x.median_rank, y, s=52, color=c, zorder=3, edgecolor=SURF, linewidth=1.5)
        ax.text(74, y, f"{100 * x.top10_freq:.0f}%", va="center", ha="right", fontsize=9, color=INK, fontweight="bold" if x.top10_freq >= 0.7 else "normal")
    ax.set_yticks(ys, [f"{i}. {short(n)}" for i, n in enumerate(e.name, 1)], fontsize=9)
    ax.set_xlim(0, 75); ax.set_xticks([1, 10, 20, 30, 40, 50, 60]); hgrid(ax, "x")
    ax.text(5.5, 10.1, "top 10", ha="center", fontsize=8.5, color=BLUE)
    ax.text(74, 10.1, "in top 10", ha="right", fontsize=8.5, color=INK2)
    ax.set_xlabel("Rank in resamples")
    ax.set_title("Batters" if r == "bat" else "Bowlers", fontsize=10.5, fontweight="bold", color=INK, pad=14)
    ax.set_ylim(-0.6, 10.4)
frame(fig, "Seven picks hold their place in at least 70% of resamples; the rest are close calls",
      "Readiness top 10, matches resampled 300 times: dot = median rank, line = 10th-90th percentile (blue = top 10 in at least 70%)",
      "Source: 03_ratings.py bootstrap, out/bat_final.csv and out/bowl_final.csv")
save(fig, "fig05_bootstrap_ranks.png")

# ---------- 6. readiness vs career: rank to rank ----------
fig, axs = plt.subplots(1, 2, figsize=(12.4, 6.4), gridspec_kw=dict(wspace=1.05))
fig.subplots_adjust(left=0.14, right=0.87, top=0.76, bottom=0.07)
counts = {}
for ax, r in zip(axs, ["bat", "bowl"]):
    R, C = fin[("readiness", r)], fin[("career", r)]
    rkR = pd.Series(range(1, len(R) + 1), index=R.index); rkC = pd.Series(range(1, len(C) + 1), index=C.index)
    tR, tC = set(R.index[:10]), set(C.index[:10]); both = tR & tC; counts[r] = len(both)
    ymax = max(max(rkC[list(tR | tC)]), max(rkR[list(tR | tC)]))
    ax.axhspan(0.5, 10.5, color=BLUE, alpha=0.05, linewidth=0)
    for p in tR | tC:
        c = BLUE if p in both else ORANGE; nm = short(R.loc[p, "name"])
        ax.plot([0, 1], [rkC[p], rkR[p]], color=c, linewidth=2 if p in both else 1.6, alpha=0.9, solid_capstyle="round")
        ax.scatter([0, 1], [rkC[p], rkR[p]], s=34, color=c, edgecolor=SURF, linewidth=1.2, zorder=3)
        ax.text(-0.06, rkC[p], f"{nm}  {rkC[p]}", ha="right", va="center", fontsize=8.5, color=INK if rkC[p] <= 10 else INK2)
        ax.text(1.06, rkR[p], f"{rkR[p]}  {nm}", ha="left", va="center", fontsize=8.5, color=INK if rkR[p] <= 10 else INK2)
    ax.set_ylim(ymax + 0.8, 0.2); ax.set_xlim(-0.05, 1.05); ax.axis("off")
    ax.text(0, -0.3, "Career", ha="center", fontsize=9.5, fontweight="bold", color=INK2)
    ax.text(1, -0.3, "Readiness", ha="center", fontsize=9.5, fontweight="bold", color=INK2)
    ax.text(0.5, ymax + 0.75, "shaded = top 10", ha="center", fontsize=8, color=BLUE)
    rho = R.score.rank().corr(C.score.reindex(R.index).rank())
    ax.set_title(f"{'Batters' if r == 'bat' else 'Bowlers'}: {len(both)} in both, rank correlation {rho:.2f}", fontsize=10.5, fontweight="bold", color=INK, pad=28, loc="center")
axs[0].plot([], [], color=BLUE, linewidth=2, label="In both top 10s"); axs[0].plot([], [], color=ORANGE, linewidth=1.6, label="In one top 10 only")
fig.legend(loc="upper right", bbox_to_anchor=(0.99, 0.975), ncol=2, fontsize=9, labelcolor=INK)
frame(fig, f"The two ratings agree: {counts['bat']} batters and {counts['bowl']} bowlers make both top 10s",
      "Rank in Career Ability (left) and Current Readiness (right) for every player in either top 10",
      "Source: 03_ratings.py, out/*_final.csv and out/*_career_final.csv; rank correlation across all eligible players")
save(fig, "fig06_readiness_vs_career.png")

# ---------- 7. split-half reliability ----------
info = json.load(open(f"{OUT}/ratings_info.json"))["reliability"]
V1 = {"bat": {"press_skill": 0.318, "baseline": 0.281, "win_impact": 0.100, "consistency": -0.029, "clutch_delta": 0.075},   # previous version (v1),
      "bowl": {"press_skill": 0.378, "baseline": 0.309, "win_impact": 0.207, "consistency": 0.214, "clutch_delta": 0.227}}  # from its ratings_info.json
comps = [("press_skill", "Pressure rating"), ("baseline", "Usual level"), ("win_impact", "Win impact"), ("consistency", "Consistency"), ("clutch_delta", "Clutch delta")]
fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.8), sharex=True, gridspec_kw=dict(wspace=0.08))
fig.subplots_adjust(left=0.13, right=0.98, top=0.76, bottom=0.13)
for ax, r in zip(axs, ["bat", "bowl"]):
    ys = np.arange(len(comps))[::-1]
    for k, (src, col, off) in enumerate([(V1[r], GREY, 0.26), (info["readiness"][r], BLUE, 0), (info["career"][r], ORANGE, -0.26)]):
        vals = [src[c] for c, _ in comps]
        ax.barh(ys + off, vals, height=0.24, color=col)
        if k == 1:
            for y, v_ in zip(ys, vals): ax.text(max(v_, 0) + 0.006, y, f"{v_:.2f}", va="center", fontsize=8, color=INK)
    ax.axvline(0, color=GREY_D, linewidth=1); hgrid(ax, "x")
    ax.set_yticks(ys, [l for _, l in comps] if r == "bat" else [""] * len(comps))
    ax.set_title("Batters" if r == "bat" else "Bowlers", fontsize=10.5, fontweight="bold", color=INK, pad=6)
    ax.set_xlabel("Split-half correlation (odd vs even matches)")
fig.legend(handles=[Patch(color=c, label=l) for c, l in [(GREY, "Previous version (v1)"), (BLUE, "Current Readiness"), (ORANGE, "Career Ability")]],
           loc="upper right", bbox_to_anchor=(0.98, 0.9), ncol=3, fontsize=9, labelcolor=INK)
frame(fig, "Both new ratings repeat at least as well as v1; batting clutch delta is still mostly noise",
      "How well each component measured on one half of the matches matches the other half (119 players per role; Readiness values labelled)",
      "Source: 03_ratings.py, out/ratings_info.json (v1 values from the previous version's ratings_info.json)")
save(fig, "fig07_reliability.png")

# ---------- 8. held-out accuracy by older-match weight ----------
if have("readiness_test.csv"):
    T = pd.read_csv(f"{OUT}/readiness_test.csv"); T = T[T.predictor == "composite"]
    m = T.groupby(["test", "role", "variant"]).r.mean()
    steps = [0.0, 0.1, 0.25, 0.5, 1.0]; xs = np.arange(len(steps))
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.9), sharey=True, gridspec_kw=dict(wspace=0.12))
    fig.subplots_adjust(left=0.07, right=0.9, top=0.76, bottom=0.17)
    for ax, r in zip(axs, ["bat", "bowl"]):
        ax.axvspan(2.65, 3.35, color=BLUE, alpha=0.07, linewidth=0)
        for t, col, lab in [("cross-half", BLUE, "Held-out matches (cross-half)"), ("out-of-time", GREY_D, "Next season (out-of-time)")]:
            ys = [m[(t, r, f"a0={s}")] for s in steps]
            ax.plot(xs, ys, color=col, linewidth=2, marker="o", markersize=6, markeredgecolor=SURF, markeredgewidth=1.5, label=lab)
            pv = m[(t, r, "previous")]; ax.hlines(pv, -0.3, 4.22, color=col, linewidth=1, linestyle=(0, (4, 3)), alpha=0.8)
            ax.text(4.32, pv, f"v1 {pv:.3f}", va="center", fontsize=8, color=INK2)
            ax.text(3, ys[3] + (0.012 if t == "cross-half" else -0.02), f"{ys[3]:.3f}", ha="center", fontsize=8.5, fontweight="bold", color=INK)
        ax.set_xticks(xs, ["0\n(last 12\nmonths only)", "0.1", "0.25", "0.5\nReadiness", "1\nCareer"], fontsize=8.5)
        hgrid(ax); ax.set_ylim(0, 0.26); ax.set_xlim(-0.3, 4.95)
        ax.set_title("Batters" if r == "bat" else "Bowlers", fontsize=10.5, fontweight="bold", color=INK, pad=6)
    axs[0].set_ylabel("Correlation with actual pressure value")
    hs = [Line2D([], [], color=BLUE, linewidth=2, marker="o", label="Held-out matches (cross-half)"),
          Line2D([], [], color=GREY_D, linewidth=2, marker="o", label="Next season (out-of-time)"),
          Line2D([], [], color=GREY_D, linewidth=1, linestyle=(0, (4, 3)), label="Previous model (v1), same test")]
    fig.legend(handles=hs, loc="upper right", bbox_to_anchor=(0.98, 0.9), ncol=3, fontsize=8.8, labelcolor=INK)
    fig.text(0.47, 0.035, "Weight of a match older than 12 months", ha="center", fontsize=9.5, color=INK2)
    frame(fig, "v2 beats v1 on held-out matches; no recency weighting forecasts next season better",
          "Composite score vs actual pressure value on data the rating did not see (20 cross-half comparisons, 3 out-of-time folds)",
          "Source: experiments/readiness_test.py, out/readiness_test.csv")
    save(fig, "fig08_heldout_by_recency.png")

# ---------- 9. robustness of the submitted lists ----------
R = pd.read_csv(f"{OUT}/robustness.csv")
order = ["Pressure = top 30% leverage", "Pressure = top 20% leverage", "Older matches weight 0.75", "Older matches weight 0.25",
         "Career Ability (all matches equal)", "Previous recency (18-month half-life)", "Equal component weights", "Pressure rating only",
         "Without bowler execution component", "Pressure = top 10% (extreme)", "IPL only", "T20I only", "Conventional RRR/wickets index", "Last 12 months only"]
P = R.set_index(["scenario", "role"])
fig, ax = plt.subplots(figsize=(8.2, 6.2)); fig.subplots_adjust(left=0.42, right=0.95, top=0.82, bottom=0.07)
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", ["#e8f1fc", "#9ec5f4", "#3987e5", "#184f95"])
for i, s in enumerate(order):
    for k, role in enumerate(["bat", "bowl"]):
        ov = P.loc[(s, role), "overlap_top10"]; rho = P.loc[(s, role), "spearman"]
        ax.add_patch(plt.Rectangle((k + 0.03, i + 0.05), 0.94, 0.9, color=cmap((ov - 3) / 7), linewidth=0))
        tc = SURF if ov >= 8 else INK
        ax.text(k + 0.5, i + 0.5, f"{ov} of 10", ha="center", va="center", fontsize=10, fontweight="bold", color=tc)
        ax.text(k + 0.92, i + 0.5, f"ρ {rho:.2f}", ha="right", va="center", fontsize=7.5, color=tc)
ax.set_xlim(0, 2); ax.set_ylim(len(order), 0); ax.set_xticks([0.5, 1.5], ["Batters", "Bowlers"]); ax.xaxis.tick_top()
ax.set_yticks(np.arange(len(order)) + 0.5, order, fontsize=9); ax.tick_params(length=0)
for sp in ax.spines.values(): sp.set_visible(False)
frame(fig, "Thresholds, weights and recency barely move the submitted lists",
      "Players of the submitted top 10 still in the top 10 when one modelling choice changes (ρ = rank correlation)",
      "Source: 04_robustness.py, out/robustness.csv")
save(fig, "fig09_robustness.png")

# ---------- 10. additions pack: three candidate additions ----------
if have("additions_test.csv"):
    A = pd.read_csv(f"{OUT}/additions_test.csv"); A = A[(A.pred == "composite") & (A.target == "raw") & A.kind.isin(["match", "venue"])]
    p = A.pivot_table(index=["kind", "role", "split"], columns="variant", values="r")
    gain = p.drop(columns="base").sub(p["base"], axis=0)
    names = [("cond_match", "Match conditions"), ("cond_venue", "Venue conditions"), ("cond_venue+match", "Venue + match conditions"),
             ("rb8", "Required-rate band (8)"), ("rb4", "Required-rate band (4)"), ("oppteam", "Team-level opponent prior"), ("all (vm+rb4+oppteam)", "All three together")]
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.8), sharex=True, gridspec_kw=dict(wspace=0.08))
    fig.subplots_adjust(left=0.2, right=0.98, top=0.76, bottom=0.14)
    for ax, r in zip(axs, ["bat", "bowl"]):
        ys = np.arange(len(names))[::-1]
        ax.axvline(0, color=GREY_D, linewidth=1.2)
        for kind, col, off in [("match", BLUE, 0.14), ("venue", ORANGE, -0.14)]:
            g = gain.loc[(kind, r)]
            mu = [g[v].mean() for v, _ in names]; better = [int((g[v] > 0).sum()) for v, _ in names]
            ax.scatter(mu, ys + off, s=46, color=col, edgecolor=SURF, linewidth=1.3, zorder=3)
            for y, x_, bt in zip(ys, mu, better): ax.text(x_ + (0.0012 if x_ >= 0 else -0.0012), y + off, f"{bt}/20", va="center", ha="left" if x_ >= 0 else "right", fontsize=7.5, color=INK2)
        ax.set_yticks(ys, [l for _, l in names] if r == "bat" else [""] * len(names)); hgrid(ax, "x"); ax.set_xlim(-0.026, 0.012); ax.set_xticks([-0.02, -0.01, 0, 0.01])
        ax.set_title("Batters" if r == "bat" else "Bowlers", fontsize=10.5, fontweight="bold", color=INK, pad=6)
        ax.set_xlabel("Change in held-out correlation vs v2 (right = better)")
    fig.legend(handles=[Line2D([], [], color=c, marker="o", linestyle="", markersize=7, label=l) for c, l in [(BLUE, "Random match splits"), (ORANGE, "Venue-disjoint splits")]], loc="upper right", bbox_to_anchor=(0.98, 0.9), ncol=2, fontsize=9, labelcolor=INK)
    frame(fig, "None of the three candidate additions beats the current model on held-out data",
          "Mean change in held-out prediction over 20 comparisons per split type; label = comparisons where the addition did better",
          "Source: experiments/additions_test.py, out/additions_test.csv (composite score, context-adjusted pressure value)")
    save(fig, "fig10_additions_test.png")

# ---------- 11. the spin edge ----------
if have("spin_edge_test.csv"):
    S = pd.read_csv(f"{OUT}/spin_edge_test.csv")
    lab = {"context cell only (current baseline)": "Same context cell (v2 baseline)", "+ opponent batter quality": "+ opponent batter quality",
           "+ match/venue level": "+ match and venue scoring level", "+ batter new/settled (within phase)": "+ batter new or settled",
           "+ same match and innings": "Same match and innings", "+ same match, innings, phase, batter new/settled": "Same match, innings, phase, batter state",
           "powerplay": "Powerplay", "middle": "Middle overs", "death": "Death overs",
           "context cell only": "Same context cell", "same match, innings, phase, batter new/settled": "Same match, innings, phase, batter state"}
    groups = [("pressure", "Pressure balls, controlling for"), ("phase", "Pressure balls, by phase"), ("normal", "Normal (non-pressure) balls, for comparison")]
    fig, ax = plt.subplots(figsize=(10.4, 6.4)); fig.subplots_adjust(left=0.33, right=0.95, top=0.84, bottom=0.1)
    y = 0; ticks, tl = [], []
    for gname, gl in groups:
        ax.text(-0.52, y - 0.1, gl, transform=matplotlib.transforms.blended_transform_factory(ax.transAxes, ax.transData), fontsize=9.5, fontweight="bold", color=INK, va="center")
        y += 1
        for _, row in S[S.group == gname].iterrows():
            c = BLUE if (gname == "pressure" and row.control.startswith("+ same match, innings, phase")) else GREY_D
            lo, hi = row.gap - 1.96 * row.se, row.gap + 1.96 * row.se
            ax.plot([lo, hi], [y, y], color=c, linewidth=2, solid_capstyle="round"); ax.scatter(row.gap, y, s=52, color=c, edgecolor=SURF, linewidth=1.4, zorder=3)
            ax.text(hi + 0.8, y, f"{row.gap:.1f}", va="center", fontsize=9, fontweight="bold", color=INK)
            ticks.append(y); tl.append(lab.get(row.control, row.control)); y += 1
        y += 0.6
    ax.set_yticks(ticks, tl, fontsize=9); ax.set_ylim(y - 0.4, -0.8); ax.axvline(0, color=GREY_D, linewidth=1.2)
    ax.set_xlim(-2, 40); hgrid(ax, "x"); ax.set_xlabel("Spin minus pace, runs per 100 balls (dot = estimate, line = 95% interval)")
    frame(fig, "Spin's pressure edge over pace stays near 15 runs per 100 balls under every control",
          "Bowler's-view value per 100 balls, spin minus pace; standard errors clustered by match",
          "Source: experiments/spin_edge_test.py, out/spin_edge_test.csv")
    save(fig, "fig11_spin_edge.png")
print("done")
