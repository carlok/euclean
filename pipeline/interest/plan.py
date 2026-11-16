"""The pre-registered design, as constants. `docs/interest-prereg.md` is the
contract; this module transcribes it so the code cannot drift from it quietly.
"""

import json

from ..kernel.theory import ROOT

PREREG = ROOT / "docs" / "interest-prereg.md"
LABEL_MANIFEST = ROOT / "docs" / "interest-labels.sha256"

try:
    # A run artifact, gitignored: a fresh clone has none, and nothing that only
    # needs the definitions (the tests, for one) should fail to import for it.
    ROLES = json.loads((ROOT / "runs" / "ensemble" / "roles.json").read_text())
except FileNotFoundError:
    ROLES = {"subject": None, "control": None}
SUBJECT, CONTROL = ROLES["subject"], ROLES["control"]
THEORIES = (SUBJECT, CONTROL)
PERMS = (0, 1, 2)
SEEDS = (0, 100)

# (theory code, permutation) -> spec file, relative to the repository root.
# Permutation 0 of each theory is the spec already public; 1 and 2 were
# exported by the owner from the non-blind side into runs/specs/. The sha256 of
# every file is in the pre-registration.
SPECS = {
    (SUBJECT, 0): "theory/spec.json",
    (CONTROL, 0): "runs/admissibility/candidate-spec.json",
    (SUBJECT, 1): f"runs/specs/{SUBJECT}-seed1.json",
    (SUBJECT, 2): f"runs/specs/{SUBJECT}-seed2.json",
    (CONTROL, 1): f"runs/specs/{CONTROL}-seed1.json",
    (CONTROL, 2): f"runs/specs/{CONTROL}-seed2.json",
}

K = 50
V_KINDS = ("loc", "term", "tac")
MODES = ("dag", "tree")
S_KINDS = ("raw", "canon")
PRIMARY = ("loc", "dag", "raw")


def variants():
    return [(x, m, s) for x in V_KINDS for m in MODES for s in S_KINDS]


def corpora():
    """Every corpus, in the fixed order that also numbers their seeds."""
    from .corpora import run_id

    return [run_id(t, p, s) for t in THEORIES for p in PERMS for s in SEEDS]


def corpus_index(run):
    return corpora().index(run)


def frozen_label_hashes():
    if not LABEL_MANIFEST.exists():
        return {}
    out = {}
    for line in LABEL_MANIFEST.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sha, run = line.split()
            out[run] = sha
    return out


def seed_record(run):
    from . import loop, stats

    return {
        "run": run,
        "corpus_index": corpus_index(run),
        "bootstrap": {"entropy": stats.ENTROPY, "resamples": stats.BOOTSTRAP,
                      "keys": "(corpus_index, analysis, variant)"},
        "loop": {"tie_seed": [corpus_index(run), 7], "random_repeats": loop.RANDOM_REPEATS,
                 "random_seeds": f"(1, s) and (2, s) for s in 0..{loop.RANDOM_REPEATS - 1}"},
    }
