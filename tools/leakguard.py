"""Fail loudly if the public tree has learned what the theory is about.

Two independent checks:

  1. vocabulary   no term from the (secret) wordlist appears in the public tree
  2. quarantine   nothing under pipeline/ reaches into secret/

The wordlist is deliberately not stored here: a public file enumerating the
domain's vocabulary would leak the domain as surely as the vocabulary would.

Exit code 0 clean, 1 on any hit.  Run after every generation batch and before
any report is written.

Output names locations only: tier and file:line. Pass `--show` to also print
the matched term and its context. Hiding is the default because the guard is
run by executors who must stay blind, and a guard that prints the wordlist to
whoever runs it leaks the thing it exists to protect. Only the repository
owner should pass `--show`.
"""

import argparse
import codecs
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
               "tools", "tests", "docs", "tex", ".github"]
# Roots that legitimately may be absent (nothing has been generated yet).
# `.github` holds CI configuration, which is published with the repository.
# Being a dot-directory it was outside every root until it was listed here.
OPTIONAL_DIRS = {"theories", "generated", "metadata", "runs", "tex", ".github"}
ARTIFACT_DIRS = {"theory", "theories", "generated", "metadata", "runs", "docs", "tex"}

SKIP_DIRS = {".git", ".lake", "__pycache__", ".DS_Store", "secret"}
SKIP_SUFFIXES = {".olean", ".ilean", ".trace", ".hash", ".pyc",
                 # typesetter output: regenerated from the source next to it,
                 # and its own logs quote package chatter that trips the
                 # artifact tier without ever being authored by anyone
                 ".log", ".aux", ".out", ".toc", ".pdf", ".gz", ".fls", ".fdb_latexmk"}


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


def _term_re(terms):
    """Match a term at an identifier boundary, not merely a word boundary.

    `\\b` treats `_` as a word character, so a term embedded in a snake_case
    identifier slipped through entirely: a listed term carrying a leading
    underscore or an `is_` prefix was invisible to this guard.

    That is stated in the abstract on purpose. An earlier draft of this very
    docstring spelled out two real listed terms to illustrate the bug, and
    tripped the check it documents. Identifiers are exactly where domain
    vocabulary hides in code, so that was the wrong boundary for the job.

    The lookbehind excludes letters and digits but permits `_`, which catches
    the identifier cases while still refusing the false positives that made
    `\\b` attractive: `line` is on the list and `pipeline` must not fire,
    because there the term is preceded by a letter.

    Residual hole, recorded rather than papered over: a term glued directly to
    a letter, with no separator and no case change, is still missed. Closing
    that needs tokenizing identifiers rather than scanning lines.

    The terms are compiled as a prefix tree rather than a flat alternation.
    Same positions match: a match starts wherever some term begins at an
    identifier boundary. A flat alternation retries every term at every
    position, which on a corpus file several hundred MB long was the
    difference between a guard run of minutes and one of hours. Where one
    listed phrase extends another, the tree reports the longer one, so the
    matched text can differ; which lines are flagged cannot.
    """
    return re.compile(_pattern(terms), re.IGNORECASE)


def _trie(terms):
    """A regex for `terms` with shared prefixes factored out. Terms are literals."""
    root = {}
    for term in terms:
        node = root
        for ch in term:
            node = node.setdefault(ch, {})
        node[""] = {}

    def emit(node):
        ends_here = "" in node
        alts = [re.escape(ch) + emit(node[ch]) for ch in sorted(k for k in node if k)]
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 and not ends_here else "(?:" + "|".join(alts) + ")"
        return body + ("?" if ends_here else "")

    return emit(root)


def _pattern(terms):
    return r"(?<![a-z0-9])(" + _trie(terms) + r")\w*"


def _term_re_bytes(terms):
    """`_term_re` for raw file bytes. Terms are ASCII, so case folding is too."""
    return re.compile(_pattern(terms).encode("ascii"), re.IGNORECASE)


def _is_utf8(data, chunk=1 << 24):
    """Validate without building the decoded string, which for a large corpus
    is several times the file's size in memory."""
    dec = codecs.getincrementaldecoder("utf-8")()
    try:
        for i in range(0, len(data), chunk):
            dec.decode(data[i:i + chunk])
        dec.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def scan_bytes(data, patterns):
    """First hit per tier per line, as (tier, line number, term, context).

    One pass over the whole file instead of one search per line: a corpus is
    a single JSON line, and splitting it doubles the memory for no gain.
    """
    hits = []
    for tier, rx in patterns:
        line, pos, seen = 1, 0, set()
        for m in rx.finditer(data):
            line += data.count(b"\n", pos, m.start())
            pos = m.start()
            if line in seen:
                continue
            seen.add(line)
            start = max(data.rfind(b"\n", 0, m.start()) + 1, m.start() - 40)
            stop = data.find(b"\n", m.end())
            stop = min(len(data) if stop < 0 else stop, m.start() + 50)
            context = data[start:stop].decode("utf-8", "replace").strip()
            hits.append((tier, line, m.group(0).decode("ascii", "replace"), context))
    order = {tier: i for i, (tier, _) in enumerate(patterns)}
    hits.sort(key=lambda h: (h[1], order[h[0]]))
    return hits


def scan_vocab(hard, artifacts):
    hard_re = _term_re_bytes(hard)
    art_re = _term_re_bytes(artifacts)
    hits = []
    for dirname in PUBLIC_DIRS + ["<root>"]:
        patterns = [("hard", hard_re)]
        if dirname in ARTIFACT_DIRS:
            patterns.append(("artifact", art_re))
        for path in (root_files() if dirname == "<root>" else walk(dirname)):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            # Files that are not UTF-8 were skipped before this scanned bytes;
            # they still are, so the set of scanned files has not changed.
            if not _is_utf8(data):
                continue
            rel = path.relative_to(ROOT)
            for tier, lineno, term, context in scan_bytes(data, patterns):
                hits.append((tier, f"{rel}:{lineno}", term, context))
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
    hard_re = _term_re(hard)
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


def report(hits, show=False):
    """Print hits. Without `show`, locations only: no term, no context."""
    print(f"leakguard: {len(hits)} violation(s)\n")
    for tier, loc, term, line in hits:
        if show:
            print(f"  [{tier}] {loc}  ({term})")
            print(f"          {line}")
        else:
            print(f"  [{tier}] {loc}")
    if not show:
        print("\nMatched terms are hidden. The repository owner can rerun with --show.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", action="store_true",
                    help="print matched terms and context (owner only; reveals the wordlist)")
    args = ap.parse_args(argv)
    assert_roots()
    hard, artifacts = load_vocab()
    hits = scan_vocab(hard, artifacts) + scan_quarantine() + scan_commit_messages(hard)
    if not hits:
        print("leakguard: clean")
        return 0
    report(hits, show=args.show)
    return 1


if __name__ == "__main__":
    sys.exit(main())
