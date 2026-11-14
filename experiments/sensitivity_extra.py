"""Extra sensitivity rows for the submitted (Readiness) lists: eligibility floor, simpler composites, one
leverage threshold for both innings, and the three candidate additions.
Usage (after the main pipeline, from the repo root): python -I experiments/sensitivity_extra.py out"""
import sys, os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = sys.argv[1]; sys.argv = [sys.argv[0], OUT]
def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
r = _load(os.path.join(HERE, "..", "03_ratings.py"), "r"); pt = _load(os.path.join(HERE, "additions_lib.py"), "additions_lib").pt
b = r.b
b["w"] = r.rating_weights(b, r.READY_OLD_WEIGHT)
b["rb4"] = np.where(b.innings == 2, np.searchsorted([1.1, 1.5, 2.1], b.need.fillna(0) / np.maximum(b.balls_rem, 1)), 0)
names = {"bat": b.groupby("striker_id").striker_name.last(), "bowl": b.groupby("bowler_id").bowler_name.last()}
bw = b[b.legal | b.is_wide | b.is_nb]
spin = (bw.assign(s=bw.pace_or_spin == "Spin").groupby("bowler_id").s.mean() > 0.5)
EX = r.execution_component(b, wcol="w")[["execution"]]
def table(role, bb=None, **o):
    t = pt(r, b if bb is None else bb, role, **o)[0]
    return t.join(EX) if role == "bowl" else t
def rank(t, role, wts=None, floor=None):
    if floor is not None: r.MIN_PB = floor
    e = r.composite(t, wts or r.WEIGHTS[role]); r.MIN_PB = 120; return e
main = {role: rank(table(role), role) for role in ["bat", "bowl"]}
top = {role: list(main[role].index[:10]) for role in main}
def show(label, role, e):
    new = list(e.index[:10]); ins = [names[role][p] for p in new if p not in top[role]]; outs = [names[role][p] for p in top[role] if p not in new]
    common = main[role].index.intersection(e.index); rho = main[role].loc[common, "score"].rank().corr(e.loc[common, "score"].rank())
    extra = f" | spinners in top 10: {int(spin.reindex(new).sum())}" if role == "bowl" else ""
    print(f"{label:<46} {role:<4} keeps {10 - len(outs):>2}/10  rho {rho:.2f}  n={len(e):<3} IN: {', '.join(ins) or '-'}  OUT: {', '.join(outs) or '-'}{extra}")
print("submitted bowlers: spinners", int(spin.reindex(top["bowl"]).sum()), " eligible bowlers spin share", round(spin.reindex(main["bowl"].index).mean(), 2))
for role in ["bat", "bowl"]:
    t = table(role)
    for fl in (100, 150, 200): show(f"Eligibility floor {fl} pressure balls", role, rank(t, role, floor=fl))
    show("Pressure rating only", role, rank(t, role, {"press_skill": 1.0}))
    if role == "bat": show("Rating + win impact (no clutch, consistency)", role, rank(t, role, {"press_skill": 0.8, "win_impact": 0.2}))
    else:
        show("Rating + execution (no clutch, cons., impact)", role, rank(t, role, {"press_skill": 0.8, "execution": 0.2}))
        show("Composite without clutch delta", role, rank(t, role, {k: v for k, v in r.WEIGHTS[role].items() if k != "clutch_delta"}))
    # one leverage threshold across both innings
    g = b.copy(); g["pressure"] = g.li >= g.li.quantile(0.75)
    if role == "bat": print("   single threshold: LI >=", round(b.li.quantile(0.75), 2), " share of pressure balls from innings 1:", round(g[g.pressure].innings.eq(1).mean(), 3), " share of innings-1 balls flagged:", round(g[g.innings == 1].pressure.mean(), 3))
    tg = pt(r, g, role)[0]; tg = tg.join(EX) if role == "bowl" else tg
    show("One leverage threshold for both innings", role, r.composite(tg, r.WEIGHTS[role], list(main[role].index)))
    for lab, o in [("Addition: match+venue conditions", dict(cond="vm")), ("Addition: required-rate band (4)", dict(rbctx="rb4")),
                   ("Addition: opponent team-level prior", dict(oppteam=True)), ("All three additions", dict(cond="vm", rbctx="rb4", oppteam=True))]:
        show(lab, role, rank(table(role, **o), role))
# who gains/loses most from conditions (information only)
for role in ["bat", "bowl"]:
    t = table(role, cond="vm"); e = main[role].join(t[["cond_press"]].rename(columns={"cond_press": "cp"}))
    e["name"] = e.index.map(names[role])
    print(role, "match+venue level on pressure balls, runs/100 (own-view): SD across eligible", round(e.cp.std(), 1), " top10:", [(n, round(v, 1)) for n, v in zip(e.name[:10], e.cp[:10])])
