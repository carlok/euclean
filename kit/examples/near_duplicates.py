"""How much of a ranking's top k is near-duplicates of itself?

Post hoc and exploratory: this was not in the audit's pre-registration. Reading
the audit's top-ranked statements showed I0's top places filled with variants of
one statement that differ in a single hypothesis; this measures it.

For each corpus in kit/data/euclean: the share of the top k that has at least
one other top-k entry one hypothesis apart (`evaluate.one_hypothesis_apart`),
under I0 (LoC, set expansion, raw size), U0, the audit's structural importance,
and random draws of k statements.

Usage:  python kit/examples/near_duplicates.py [--k 50] [--out FILE]
"""

import argparse
import json
import pathlib
import random
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from interestkit import Library, evaluate, metric  # noqa: E402

DATA = HERE.parent / "data" / "euclean"


def analyse(path, k, draws, seed):
    lib = Library.load(path)
    thms = lib.theorems()
    names = [d["name"] for d in thms]
    text = {d["name"]: d["statement"] for d in thms}
    i0 = {n: metric.log10(v) for n, v in metric.i0(lib, "loc", "dag", metric.s_raw).items()}
    u0 = metric.u0(lib, "loc", "dag")
    imp = {d["name"]: d["reference"]["importance"] for d in thms}
    out = {"run": lib.meta.get("run"), "role": lib.meta.get("role"), "statements": len(names)}
    for key, scores in (("I0", i0), ("U0", u0), ("importance", imp)):
        top = evaluate.rank(scores, names)[:k]
        out[key] = evaluate.near_duplicate_share(text[n] for n in top)
    rnd = random.Random(f"near-duplicates-{seed}-{path.stem}")
    out["random_mean"] = statistics.mean(
        evaluate.near_duplicate_share(text[n] for n in rnd.sample(names, k)) for _ in range(draws))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out")
    args = ap.parse_args()
    manifest = json.loads((DATA / "MANIFEST.json").read_text())
    rows = [analyse(DATA / c["file"], args.k, args.draws, args.seed) for c in manifest["corpora"]]
    result = {"k": args.k, "draws": args.draws, "seed": args.seed, "post_hoc": True, "corpora": rows}
    for r in rows:
        print(f"{r['run']:28s} I0 {r['I0']:.2f}  U0 {r['U0']:.2f}  importance {r['importance']:.2f}  "
              f"random {r['random_mean']:.2f}")
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, indent=1) + "\n")


if __name__ == "__main__":
    main()
