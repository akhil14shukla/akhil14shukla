"""Train the routing classifier and report whether semantics earned its place.

Runs an ablation by default -- structural signals alone, embeddings alone, and
both -- because the whole question is whether reading the prompt's meaning adds
anything over the features ccrouter already computes.

Accuracy is not the headline. Routing errors are asymmetric: sending hard work
to a small model costs a retry and a bad answer, while sending easy work to a
big one costs a few cents. `routing_cost` below prices that asymmetry, and it
is the number to optimise.

    python3 ml/train.py --data ml/dataset/*.jsonl --out ml/dataset/model.npz
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import DEFAULT_ENCODER, STRUCTURAL_KEYS, Featurizer, stack
from schema import TIERS, describe, dedupe, read, split

# Cost of predicting tier j when the truth is tier i, in "retries equivalent".
# Under-routing is charged 1.0 per tier missed; over-routing 0.3.
UNDER_COST, OVER_COST = 1.0, 0.3


def cost_matrix() -> np.ndarray:
    n = len(TIERS)
    matrix = np.zeros((n, n), dtype=np.float64)
    for truth in range(n):
        for pred in range(n):
            gap = pred - truth
            matrix[truth, pred] = -gap * UNDER_COST if gap < 0 else gap * OVER_COST
    return matrix


COSTS = cost_matrix()


def routing_cost(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(COSTS[y_true, y_pred].mean())


def _report(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score

    under = float((y_pred < y_true).mean())
    over = float((y_pred > y_true).mean())
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "under_route": under,
        "over_route": over,
        "routing_cost": routing_cost(y_true, y_pred),
    }
    print(f"  {name:<26} acc={metrics['accuracy']:.3f}  F1={metrics['macro_f1']:.3f}  "
          f"under={under:.3f}  over={over:.3f}  cost={metrics['routing_cost']:.4f}")
    return metrics


def _confusion(y_true: np.ndarray, y_pred: np.ndarray) -> str:
    from sklearn.metrics import confusion_matrix

    matrix = confusion_matrix(y_true, y_pred, labels=range(len(TIERS)))
    header = "            " + "".join(f"{t:>9}" for t in TIERS) + "   (predicted)"
    rows = [header]
    for index, tier in enumerate(TIERS):
        rows.append(f"  true {tier:<6}" + "".join(f"{v:>9}" for v in matrix[index]))
    return "\n".join(rows)


def _fit(kind: str, X, y, weights):
    if kind == "logreg":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced"),
        )
        model.fit(X, y, logisticregression__sample_weight=weights)
        return model

    if kind == "gbt":
        try:
            from xgboost import XGBClassifier

            model = XGBClassifier(
                n_estimators=400, max_depth=5, learning_rate=0.08,
                subsample=0.9, colsample_bytree=0.8, tree_method="hist",
                objective="multi:softprob", num_class=len(TIERS),
            )
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingClassifier

            model = HistGradientBoostingClassifier(
                max_iter=400, learning_rate=0.08, max_depth=6,
                class_weight="balanced",
            )
        model.fit(X, y, sample_weight=weights)
        return model

    raise ValueError(f"unknown model {kind!r}")


def export_npz(model, path: str, encoder: str, blocks: str) -> None:
    """Export a linear model to plain arrays so runtime needs only numpy."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = model[0] if isinstance(model[0], StandardScaler) else None
    clf = model[-1]
    if not isinstance(clf, LogisticRegression):
        raise TypeError("only the linear model exports to npz; GBT stays offline")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        coef=clf.coef_.astype(np.float32),
        intercept=clf.intercept_.astype(np.float32),
        mean=(scaler.mean_ if scaler is not None else np.zeros(clf.coef_.shape[1])).astype(np.float32),
        scale=(scaler.scale_ if scaler is not None else np.ones(clf.coef_.shape[1])).astype(np.float32),
        classes=np.array(TIERS),
        structural_keys=np.array(STRUCTURAL_KEYS),
        encoder=np.array(encoder),
        blocks=np.array(blocks),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", nargs="+", default=["ml/dataset/*.jsonl"])
    parser.add_argument("--out", default="ml/dataset/model.npz")
    parser.add_argument("--encoder", default=DEFAULT_ENCODER)
    parser.add_argument("--model", default="logreg", choices=("logreg", "gbt"))
    parser.add_argument("--blocks", default="both", choices=("both", "semantic", "structural"))
    parser.add_argument("--no-ablation", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)

    paths = [p for pattern in args.data for p in sorted(glob.glob(pattern))
             if not p.endswith("model.npz")]
    rows = dedupe(read(*paths))
    if not rows:
        print(f"no data found in {args.data}", file=sys.stderr)
        return 1

    print(f"loaded {len(paths)} file(s)")
    print(describe(rows), "\n")

    parts = split(rows)
    for name, subset in parts.items():
        print(f"  {name:<6} {len(subset):>5} rows")
    if not parts["test"]:
        print("\n!! test split is empty -- seed data is train-only by design.\n"
              "   Add mined or hand-labelled rows before trusting any number here.",
              file=sys.stderr)
        return 2
    print()

    featurizer = Featurizer(encoder_name=args.encoder)
    encoded = {
        name: featurizer.transform(subset) for name, subset in parts.items() if subset
    }
    labels = {
        name: np.array([TIERS.index(e.label) for e in subset])
        for name, subset in parts.items() if subset
    }
    weights = {
        name: np.array([e.weight for e in subset], dtype=np.float64)
        for name, subset in parts.items() if subset
    }

    blocks = ("structural", "semantic", "both") if not args.no_ablation else (args.blocks,)
    results: dict[str, dict[str, float]] = {}
    trained: dict[str, object] = {}

    for block in blocks:
        X_train = stack(*encoded["train"], block=block)
        model = _fit(args.model, X_train, labels["train"], weights["train"])
        trained[block] = model
        print(f"{args.model} on {block} features ({X_train.shape[1]} dims)")
        for name in ("val", "test"):
            if name in encoded:
                y_pred = model.predict(stack(*encoded[name], block=block))
                results[f"{block}/{name}"] = _report(name, labels[name], y_pred)
        print()

    best_block = args.blocks if args.no_ablation else min(
        blocks, key=lambda b: results.get(f"{b}/test", {}).get("routing_cost", 9e9)
    )
    print(f"best by routing cost on test: {best_block}\n")
    y_pred = trained[best_block].predict(stack(*encoded["test"], block=best_block))
    print(_confusion(labels["test"], y_pred), "\n")

    if args.model == "logreg":
        export_npz(trained[best_block], args.out, args.encoder, best_block)
        print(f"exported {args.out}  (numpy-only runtime, blocks={best_block})")
    else:
        print("gbt models are offline-only; rerun with --model logreg to export")

    if args.report:
        Path(args.report).write_text(json.dumps(
            {"results": results, "best_block": best_block,
             "n": {k: len(v) for k, v in parts.items()}}, indent=2))
        print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
