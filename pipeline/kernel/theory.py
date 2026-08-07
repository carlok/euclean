"""Loading the theory. This is the pipeline's only channel to the axioms."""

import json
import pathlib

from . import formula as F

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "theory" / "spec.json"


class Theory:
    def __init__(self, spec):
        self.sort = spec["sort"]
        self.relations = dict(spec["relations"])
        self.seed = spec.get("seed")
        self.axiom_names = [a["name"] for a in spec["axioms"]]
        self.env = {a["name"]: F.normalize(a["formula"]) for a in spec["axioms"]}

    def statement(self, name):
        return self.env[name]

    def arity(self, rel):
        return self.relations[rel]

    def __repr__(self):
        return (
            f"Theory(sort={self.sort!r}, relations={self.relations}, "
            f"axioms={len(self.axiom_names)}, seed={self.seed})"
        )


def load(path=SPEC):
    return Theory(json.loads(pathlib.Path(path).read_text()))
