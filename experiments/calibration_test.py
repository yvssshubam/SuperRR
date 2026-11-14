"""Compare calibration methods and team strength for the win-probability model on held-out matches.
Usage (after the main pipeline): python -I experiments/calibration_test.py out
Every method starts from the raw Markov probability (wp_raw, before calibration) and is
scored on matches held out by 5-fold cross-validation grouped by match."""
import sys, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
b = pd.read_pickle(f"{sys.argv[1]}/balls_scored.pkl")
eps = 1e-4
lg = lambda p: np.log(np.clip(p, eps, 1 - eps) / (1 - np.clip(p, eps, 1 - eps)))
def ece(p, y):
    d = pd.DataFrame({"p": p, "y": y, "b": pd.cut(p, np.linspace(0, 1, 11), include_lowest=True)})
    g = d.groupby("b", observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    return float((g.n * (g.p - g.y).abs()).sum() / len(d))
rows = []
for inn in (1, 2):
    d = b[b.innings == inn]; x = lg(d.wp_raw.values); y = d.bat_won.values; g = d.match_id.values
    X = np.c_[x, d.elo_bat.values]
    P = {k: np.zeros(len(d)) for k in ["platt", "isotonic", "platt_per_format", "platt_plus_elo"]}
    for tr, te in GroupKFold(5).split(d, groups=g):
        P["platt"][te] = LogisticRegression(C=1e6).fit(x[tr, None], y[tr]).predict_proba(x[te, None])[:, 1]
        P["isotonic"][te] = IsotonicRegression(out_of_bounds="clip", y_min=.001, y_max=.999).fit(x[tr], y[tr]).predict(x[te])
        for e in np.unique(d.env.values):
            a, c = tr[d.env.values[tr] == e], te[d.env.values[te] == e]
            P["platt_per_format"][c] = LogisticRegression(C=1e6).fit(x[a, None], y[a]).predict_proba(x[c, None])[:, 1]
        P["platt_plus_elo"][te] = LogisticRegression(C=1e6).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    for k, p in P.items():
        rows.append(dict(innings=inn, method=k, logloss=round(log_loss(y, np.clip(p, eps, 1 - eps)), 4),
                         brier=round(brier_score_loss(y, p), 4), auc=round(roc_auc_score(y, p), 4), ece_pts=round(100 * ece(p, y), 2)))
print(pd.DataFrame(rows).to_string(index=False))
