"""Loading the theory. This is the pipeline's only channel to the axioms.

`name` and `spec_hash` exist so that an artifact can say which axioms produced
it. The generator rewrites `theory/spec.json` in place as it cycles theories and
identifier permutations, and a measurement taken against the wrong one has
already happened once: a seed-0 corpus was compared against a seed-1 theory,
produced a plausible 0%, and was caught only because a one-step axiom failed to
unify with its own instance.

The hash covers the axioms, relations and sort — everything the pipeline reasons
from — so two specs agreeing on it are interchangeable for any measurement.
"""

import hashlib
import json
import pathlib

from . import formula as F

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "theory" / "spec.json"

DEFAULT_NAME = "incumbent"


def spec_hash(spec):
    """A fingerprint of one *labelling* of a theory.

    Not invariant under relabelling, and that is the correct behaviour here even
    though it reads like a limitation. The failure this exists to catch is
    Python reasoning about one spec while Lean checks against another, and the
    concrete case was a seed-0 corpus measured against a seed-1 theory. A
    relabelling-invariant hash would call those two identical and miss it.

    The `seed` field is excluded because it is metadata rather than content: two
    specs with the same axioms under the same names are interchangeable whatever
    number is recorded beside them. Permuting the identifiers *does* change the
    hash, because it changes the formulas.

    If a "same theory up to renaming" test is ever needed, canonicalize the
    relation names through `canon/relations.canonical_map` first. Nothing needs
    that today.
    """
    payload = {
        "sort": spec["sort"],
        "relations": dict(sorted(spec["relations"].items())),
        "axioms": sorted(
            (a["name"], json.dumps(a["formula"], sort_keys=True)) for a in spec["axioms"]
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


class Theory:
    def __init__(self, spec):
        self.sort = spec["sort"]
        self.relations = dict(spec["relations"])
        self.seed = spec.get("seed")
        self.name = spec.get("theory", DEFAULT_NAME)
        self.spec_hash = spec_hash(spec)
        self.axiom_names = [a["name"] for a in spec["axioms"]]
        self.env = {a["name"]: F.normalize(a["formula"]) for a in spec["axioms"]}

    def statement(self, name):
        return self.env[name]

    def arity(self, rel):
        return self.relations[rel]

    def __repr__(self):
        return (
            f"Theory(name={self.name!r}, sort={self.sort!r}, relations={self.relations}, "
            f"axioms={len(self.axiom_names)}, seed={self.seed}, hash={self.spec_hash})"
        )


def load(path=SPEC):
    return Theory(json.loads(pathlib.Path(path).read_text()))
