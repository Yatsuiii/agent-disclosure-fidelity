# Session Contract

Objective: Prepare this repository's front door for public release, so a
grant reviewer arriving from an external listing lands on an accurate
statement of what has been measured. The current README.md predates the
agent-side pilot entirely and says "Status: scaffolding. No measurements
have been taken yet, and no result in this repo should be cited," which is
false as of commit 81d7b66: the pilot has an armed mechanism-dependence
result (10/10 both directions), a 50-trial mechanism-selection result, a
10-prompt adversarial pass, and a cross-harness check. Rewrite README.md
only. No code, no results, no claims change.

Binding constraint: the README must not state a number the results
documents do not support, and must not present the cross-harness opencode
arm at the same evidence bar as the Claude Code arms. Where PILOT_RESULTS.md
pools all three arms into 0/50, the README shows the composition (30 Claude
Code trials plus 20 opencode trials) so a reader can see what the
denominator is made of rather than taking the pooled figure on trust.

Addendum (same session, same objective, extended on explicit instruction).
The package metadata carries the same stale framing the README carried:
`name = "shutdown-integrity"` and a description reading "Benchmark for
session termination and isolation guarantees in agent runtime SDKs". That
is the text any package index or tooling surface shows, so leaving it
correct only in README.md would leave the old project name as the
machine-readable identity. Extend the allowed files to include
pyproject.toml, changing the distribution name, the description, and adding
a readme pointer only.

Addendum allowed files (adds to the list below):
- pyproject.toml (metadata only: `name`, `description`, `readme`. No change
  to dependencies, optional-dependencies, requires-python, build-system,
  the hatch wheel packages entry, or the ruff config.)

Addendum non-goals:
- The import package stays `src/shutdown_integrity`. Only the distribution
  name changes. A distribution name differing from its import name is
  ordinary and the README already explains the history; renaming the import
  package would churn every import and every test for no evidential gain.
- The internal string identifiers that happen to contain "shutdown-integrity"
  (`shutdown-integrity-fixture-server` and `shutdown-integrity-adapter` in
  the TypeScript adapter, the smithery fake key and namespace) are not
  touched. They are protocol-level names inside fixtures, unrelated to the
  distribution name, and changing them would alter code under test in a
  documentation checkpoint.
- No LICENSE file is added here. The repository currently has none, which
  means default all-rights-reserved on a repo whose listing says the code is
  public. That is flagged for a decision, not resolved silently, because the
  licence choice is the author's.

Addendum acceptance gates:
F1. `pyproject.toml` diff touches only `name`, `description`, and an added
    `readme` key.
F2. `pip install -e .` style resolution still works: the wheel packages
    entry still points at `src/shutdown_integrity`, and `ruff check src/`
    and the test suite still pass unchanged.
F3. No source file under src/ or tests/ is modified.

Second addendum (same session, explicit instruction: Apache-2.0). The
repository has no LICENSE, which means default all-rights-reserved on a
repo whose public listing says the code and results are public. Add the
Apache License 2.0 verbatim plus a copyright notice, and declare it in
package metadata so the licence travels with the distribution rather than
only sitting in a file.

Second addendum allowed files (adds to the list below):
- LICENSE (new: Apache-2.0 terms verbatim, copyright 2026 Raghav Sharma)
- pyproject.toml (extends the metadata-only allowance above to include the
  `license` key)

Second addendum acceptance gates:
G1. The licence terms in LICENSE are byte-identical to an existing verbatim
    Apache-2.0 text already on this machine, diffed rather than retyped, so
    no clause is silently altered. Only the copyright notice differs.
    Correction after first push: the initial source was a 182-line copy with
    the APPENDIX stripped, and GitHub's detector read the result as
    NOASSERTION/Other, so the repository sidebar contradicted the README's
    licence claim. Replaced with the canonical 201-line text (APPENDIX
    intact), which differs from its source on exactly one line, the
    copyright notice. Verified by diff, and by re-querying the GitHub
    licence API after pushing rather than assuming the fix worked.
G2. `pyproject.toml` declares the licence and the editable install still
    resolves, verified in a throwaway venv, not assumed.
G3. No source file under src/ or tests/ is modified.

Branch: master

Parent: HEAD (81d7b66, adversarial task design checkpoint, already
committed)

Allowed files:
- README.md (rewrite in place)
- .claude/SESSION_CONTRACT.md

Non-goals:
- No changes to PILOT_RESULTS.md, DESIGN.md, DISCOVERY.md, HANDOFF.md, or
  PILOT_BRIEF.md. Their numbers are the source of truth the README cites;
  editing them in the same change would make the citation circular.
- No changes to any file under src/ or tests/. This is a documentation
  checkpoint, not a code checkpoint.
- No new measurements, no re-runs, no trials of any kind.
- No git remote added, no repository created on GitHub, no push. Publishing
  is a separate, explicitly authorized step, per the global rule that
  nothing lands in a public repo unread.
- No renaming of the `shutdown_integrity` Python package or the local
  directory. The package name is historical and the README explains it;
  renaming would churn every import for no evidential gain.

Baseline: working tree clean at 81d7b66, verified this session. `ruff check
src/` and `pytest tests/` state is unchanged by this checkpoint because no
code is touched.

Acceptance gates:
1. README.md contains no claim absent from PILOT_RESULTS.md or DISCOVERY.md,
   verified by citing the section each number comes from.
2. The false "no measurements have been taken yet" status line is gone, and
   the replacement status line states what is armed and what is not.
3. The results table separates the Claude Code arms from the opencode
   cross-harness arm and labels the latter's lower evidence bar explicitly.
4. The scope limits a reader needs before citing anything (Linux-only
   probe, workdir-scoped filesystem probe, no fd/socket, no credential or
   scheduled-job coverage, single model, n bounds) are on the README itself,
   not only one click away in PILOT_RESULTS.md.
5. `git status` shows only README.md and this contract modified.

Verification:
- `git diff --stat` shows exactly two files.
- Every numeric claim in README.md grepped back to its source line in
  PILOT_RESULTS.md before the checkpoint is called done.
- Read end to end by Raghav before any publish step is taken.

Status: active
