"""Rewrite stored artifacts from role names to theory codes.

`incumbent` and `candidate` were doing two jobs: naming a theory and naming its
side of a comparison. With more than two theories those come apart, so theories
are identified by an opaque code and roles become parameters. Everything already
on disk predates that and still says the old words.

Nothing is recomputed. Each artifact's `theory` field is a label, so this is a
rename over stored JSON, not a re-run.

Reads `secret/` for the mapping, which is allowed here: the quarantine forbids
`pipeline/` from reaching into it, not `tools/`. `tools/leakguard.py` does the
same thing for the same reason.

Usage:
  python3 tools/migrate_theory_names.py --dry-run
  python3 tools/migrate_theory_names.py
"""

import argparse
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "secret"))

try:
    import theory_codes as codes  # noqa: E402
    import theory_spec as spec  # noqa: E402
except ImportError:
    sys.exit("migrate: secret/ is not present, so the mapping cannot be derived")

MAPPING = {role: codes.code(domain) for role, domain in spec.LEGACY_ROLES.items()}


def _census():
    """Members per theory label, the invariant the migration must preserve."""
    c = Counter()
    for p in sorted((ROOT / "runs" / "ens").glob("*/summary.json")):
        c[json.loads(p.read_text()).get("theory", "incumbent")] += 1
    return c


def migrate_summaries(dry_run):
    changed = 0
    for p in sorted((ROOT / "runs" / "ens").glob("*/summary.json")):
        s = json.loads(p.read_text())
        # absent means the artifact predates the field entirely, and every such
        # member is the original theory
        old = s.get("theory", "incumbent")
        if old not in MAPPING:
            continue  # already a code, or a theory this script does not know
        s["theory"] = MAPPING[old]
        if not dry_run:
            p.write_text(json.dumps(s, indent=1) + "\n")
        changed += 1
    return changed


def migrate_bundles(dry_run):
    """`availability-<label>.json` carries the label in its name and inside."""
    moved = []
    ens = ROOT / "runs" / "ensemble"
    for role, code in MAPPING.items():
        src = ens / f"availability-{role}.json"
        if not src.exists():
            continue
        b = json.loads(src.read_text())
        b["label"] = code
        dst = ens / f"availability-{code}.json"
        if not dry_run:
            dst.write_text(json.dumps(b, indent=1) + "\n")
            src.unlink()
        moved.append((src.name, dst.name))
    return moved


def migrate_reports(dry_run):
    """Labels recorded inside the analysis outputs."""
    touched = []
    for name in ("stability.json", "controlverdict.json"):
        p = ROOT / "runs" / "ensemble" / name
        if not p.exists():
            continue
        text = p.read_text()
        new = text
        for role, code in MAPPING.items():
            new = new.replace(f'"{role}"', f'"{code}"')
        if new != text:
            if not dry_run:
                p.write_text(new)
            touched.append(name)
    return touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("  mapping:")
    for role, code in sorted(MAPPING.items()):
        print(f"    {role:12s} -> {code}")

    before = _census()
    print(f"\n  before: {dict(before)}")

    n = migrate_summaries(args.dry_run)
    moved = migrate_bundles(args.dry_run)
    touched = migrate_reports(args.dry_run)

    print(f"  summaries rewritten: {n}")
    for a, b in moved:
        print(f"  bundle: {a} -> {b}")
    print(f"  reports relabelled: {touched or 'none'}")

    if args.dry_run:
        print("\n  dry run, nothing written")
        return

    after = _census()
    print(f"  after:  {dict(after)}")

    # The counts must match one-for-one under the mapping. A theory that gained
    # or lost members means the rename merged two grids or dropped one, which is
    # exactly the failure a rename can cause silently.
    expected = Counter({MAPPING.get(k, k): v for k, v in before.items()})
    if after != expected:
        raise SystemExit(f"member counts changed: expected {dict(expected)}, got {dict(after)}")
    print("  member counts preserved exactly")


if __name__ == "__main__":
    main()
