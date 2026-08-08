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
    """A stable fingerprint of the axioms a spec defines.

    Deliberately excludes `seed`: re-permuting identifiers produces a different
    labelling of the same theory, and an artifact should be able to say the
    axioms are the same while the labels differ.
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
