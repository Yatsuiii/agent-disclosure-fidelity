"""Pilot orchestration: controls first, then episodes, then a JSON report.

Controls gate everything (PILOT_BRIEF.md): if either fails, this stops and
reports the abort rather than running episodes. Invoke as a module:
`python -m shutdown_integrity.pilot.run <run_root>`.
"""

import dataclasses
import json
import os
import signal
import sys
from pathlib import Path

from shutdown_integrity.pilot.episode import EvidenceBundle, run_episode
from shutdown_integrity.pilot.tasks import EPISODES, NEGATIVE_CONTROL, POSITIVE_CONTROL


def _cleanup(bundle: EvidenceBundle) -> None:
    """Kills every residual an episode left, by pid. PILOT_BRIEF.md: "clean up
    every process the pilot spawns" is a hard requirement, not best-effort;
    an episode's own residual is evidence to record, not something to leave
    running on the machine afterward.
    """
    for detail in bundle.residual_processes:
        pid = detail.get("pid")
        if not pid:
            continue
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, ValueError):
            pass


def _bundle_to_dict(bundle: EvidenceBundle) -> dict:
    data = dataclasses.asdict(bundle)
    data["task"] = dataclasses.asdict(bundle.task)
    data["fs_delta"] = dataclasses.asdict(bundle.fs_delta)
    data["workdir"] = str(bundle.workdir)
    return data


def check_controls(run_root: Path) -> tuple[bool, EvidenceBundle, EvidenceBundle]:
    """Runs both controls. Returns (both_passed, positive_bundle, negative_bundle).

    Positive control passes if it leaves a residual process. Negative control
    passes if it leaves zero residuals and zero filesystem delta. Per
    PILOT_BRIEF.md, a detector that has never been shown to trip is not a
    detector, so both directions are checked, not just one.
    """
    positive = run_episode(POSITIVE_CONTROL, run_root)
    _cleanup(positive)
    negative = run_episode(NEGATIVE_CONTROL, run_root)
    _cleanup(negative)
    positive_ok = not positive.aborted and len(positive.residual_processes) > 0
    negative_ok = not negative.aborted and not negative.residual_processes and negative.fs_delta.is_empty
    return positive_ok and negative_ok, positive, negative


def main(run_root: Path) -> int:
    run_root.mkdir(parents=True, exist_ok=True)
    controls_ok, positive, negative = check_controls(run_root)

    report: dict = {
        "controls_passed": controls_ok,
        "positive_control": _bundle_to_dict(positive),
        "negative_control": _bundle_to_dict(negative),
    }

    if not controls_ok:
        report["episodes"] = []
        report["aborted"] = True
        report["abort_reason"] = "controls did not both pass; no episode is interpretable"
        (run_root / "report.json").write_text(json.dumps(report, indent=2))
        print("ABORTED: controls did not both pass. See report.json.", file=sys.stderr)
        return 1

    episodes = []
    for task in EPISODES:
        bundle = run_episode(task, run_root)
        _cleanup(bundle)
        episodes.append(bundle)
    report["episodes"] = [_bundle_to_dict(bundle) for bundle in episodes]
    report["aborted"] = False
    (run_root / "report.json").write_text(json.dumps(report, indent=2))
    print(f"Pilot run complete. {len(episodes)} episodes. Report at {run_root / 'report.json'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m shutdown_integrity.pilot.run <run_root>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
