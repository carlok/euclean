"""Fail loudly if the public tree has learned what the theory is about.

Two independent checks:

  1. vocabulary   no term from the (secret) wordlist appears in the public tree
  2. quarantine   nothing under pipeline/ reaches into secret/

The wordlist is deliberately not stored here: a public file enumerating the
domain's vocabulary would leak the domain as surely as the vocabulary would.

Exit code 0 clean, 1 on any hit.  Run after every generation batch and before
any report is written.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VOCAB = ROOT / "secret" / "forbidden_vocab.txt"

# Declared public roots. A root listed here that does not exist is a hard
# error, not a silent skip: the failure mode this prevents is moving the theory
# to a new directory and getting "clean" from a guard that never opened it.
PUBLIC_DIRS = ["theory", "theories", "pipeline", "generated", "metadata", "runs",
               "tools", "tests", "docs", "tex"]
# Roots that legitimately may be absent (nothing has been generated yet).
OPTIONAL_DIRS = {"theories", "generated", "metadata", "runs", "tex"}
ARTIFACT_DIRS = {"theory", "theories", "generated", "metadata", "runs", "docs", "tex"}

SKIP_DIRS = {".git", ".lake", "__pycache__", ".DS_Store", "secret"}
SKIP_SUFFIXES = {".olean", ".ilean", ".trace", ".hash", ".pyc"}


def load_vocab():
    if not VOCAB.exists():
        sys.exit(f"leakguard: wordlist missing at {VOCAB} — cannot verify anything")
    hard, artifacts, section = [], [], None
    for raw in VOCAB.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line.strip("[]")
            continue
        (hard if section == "hard" else artifacts).append(line.lower())
    return hard, artifacts


def assert_roots():
    """Every mandatory public root must exist before anything is scanned.

    This cannot live inside `walk`: `walk` is a generator, so its body does not
    run until it is iterated, and a check placed there fires late or not at all.
    The property being enforced — never report clean on a tree that was not
    scanned — has to be settled up front.
    """
    missing = [d for d in PUBLIC_DIRS if d not in OPTIONAL_DIRS and not (ROOT / d).exists()]
    if missing:
        sys.exit(
            f"leakguard: declared public root(s) {missing} are missing. Refusing to "
            f"report clean on a tree it has not scanned."
        )


def walk(dirname):
    base = ROOT / dirname
    if not base.exists():
        return
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        yield path


def root_files():
    """Top-level files. Without this, anything dropped at the repo root — a
    handoff note, a scratch plan — is outside the guard entirely."""
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix not in SKIP_SUFFIXES and not path.name.startswith("."):
            yield path


def scan_vocab(hard, artifacts):
    hard_re = re.compile(r"\b(" + "|".join(hard) + r")\w*", re.IGNORECASE)
    art_re = re.compile(r"\b(" + "|".join(artifacts) + r")\w*", re.IGNORECASE)
    hits = []
    for dirname in PUBLIC_DIRS + ["<root>"]:
        patterns = [("hard", hard_re)]
        if dirname in ARTIFACT_DIRS:
            patterns.append(("artifact", art_re))
        for path in (root_files() if dirname == "<root>" else walk(dirname)):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for tier, pat in patterns:
                    m = pat.search(line)
                    if m:
                        rel = path.relative_to(ROOT)
                        hits.append((tier, f"{rel}:{lineno}", m.group(0), line.strip()[:90]))
    return hits


def scan_quarantine():
    """pipeline/ must not import, open, or path-join its way into secret/."""
    pat = re.compile(r"secret", re.IGNORECASE)
    hits = []
    for dirname in ("pipeline",):
        for path in walk(dirname):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    rel = path.relative_to(ROOT)
                    hits.append(("quarantine", f"{rel}:{lineno}", "secret", line.strip()[:90]))
    return hits


def scan_commit_messages(hard):
    """Commit messages are part of the repository and were never checked.

    Everything above walks the working tree. A commit message is not in the
    working tree, so for eight sprints this channel had no coverage at all —
    and unlike a file, a pushed message cannot be fixed by editing it.

    Only the hard tier applies. Messages are prose, and the artifact tier exists
    precisely because ordinary English words are unremarkable in prose.

    Scanned range: commits not yet on the upstream branch, because those are the
    ones that can still be amended. Anything already pushed needs a decision
    from the repository owner rather than a failing check on every later run.
    """
    hard_re = re.compile(r"\b(" + "|".join(hard) + r")\w*", re.IGNORECASE)
    try:
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        ).stdout.strip()
        rng = f"{upstream}..HEAD" if upstream else "HEAD"
        out = subprocess.run(
            ["git", "log", "--format=%h%x00%B%x00%x00", rng],
            cwd=ROOT, capture_output=True, text=True, check=False,
        ).stdout
    except OSError:
        return []

    hits = []
    for entry in out.split("\x00\x00"):
        if "\x00" not in entry:
            continue
        sha, body = entry.split("\x00", 1)
        for lineno, line in enumerate(body.splitlines(), 1):
            m = hard_re.search(line)
            if m:
                hits.append(
                    ("commit-msg", f"{sha.strip()}:{lineno}", m.group(0), line.strip()[:90])
                )
    return hits


def main():
    assert_roots()
    hard, artifacts = load_vocab()
    hits = scan_vocab(hard, artifacts) + scan_quarantine() + scan_commit_messages(hard)
    if not hits:
        print("leakguard: clean")
        return 0
    print(f"leakguard: {len(hits)} violation(s)\n")
    for tier, loc, term, line in hits:
        print(f"  [{tier}] {loc}  ({term})")
        print(f"          {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
