"""Drive the ensemble across several anonymizations of the theory.

This lives outside `pipeline/` on purpose. Re-permuting the opaque identifiers
means regenerating the theory, and the generator that does that necessarily
knows the interpretation. Keeping the call here preserves the rule the whole
experiment rests on: nothing under `pipeline/` reaches into the hidden tree, and
the discovery code only ever sees whatever anonymous theory it is handed.

Each theory seed produces a differently-labelled but structurally identical
theory. Results are compared through arity-canonical relation names, so the
comparison never needs the mapping back.

Usage:  python3 tools/ensemble_driver.py --theory-seeds 0 1 2 --generations 3
"""

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "secret" / "gen_theory.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theory-seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--min-support", type=int, default=8)
    ap.add_argument("--restore-seed", type=int, default=0)
    args = ap.parse_args()

    if not GENERATOR.exists():
        sys.exit(
            f"generator missing at {GENERATOR}. The anonymized theory has to be "
            "produced before anything can be run against it."
        )

    for seed in args.theory_seeds:
        print(f"\n=== theory seed {seed} ===")
        subprocess.run(
            [sys.executable, str(GENERATOR), "--seed", str(seed)], cwd=ROOT, check=True
        )
        subprocess.run(
            [
                sys.executable,
                # unbuffered: the child can run for minutes, and without this its
                # progress is lost entirely if the run is interrupted
                "-u",
                "-m",
                "pipeline.ensemble.run",
                "--generations",
                str(args.generations),
                "--repeats",
                str(args.repeats),
                "--min-support",
                str(args.min_support),
                "--tag",
                f"t{seed}",
            ],
            cwd=ROOT,
            check=True,
        )

    # leave the tree on a known theory so later single runs are reproducible
    subprocess.run(
        [sys.executable, str(GENERATOR), "--seed", str(args.restore_seed)], cwd=ROOT, check=True
    )
    print(f"\nrestored theory seed {args.restore_seed}")


if __name__ == "__main__":
    main()
