"""Seed GitHub labels, milestones and issues from docs/tickets/S*-*.md. Idempotent.

Usage:
    uv run python scripts/seed_issues.py [--repo owner/name] [--done-sha <sha>] [--dry-run]

Each ticket file starts with front matter: title, labels (comma separated), milestone,
status (done|open|blocked). The slice label is derived from the file name prefix.
Tickets with status `done` are created and immediately closed, referencing --done-sha.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = sorted((ROOT / "docs" / "tickets").glob("S*-*.md"))

LABELS: dict[str, tuple[str, str]] = {
    "type:feature": ("1D76DB", "User-facing behaviour"),
    "type:infra": ("5319E7", "Terraform / AWS"),
    "type:docs": ("0E8A16", "Documentation and ADRs"),
    "type:test": ("FBCA04", "Tests and verification"),
    "type:chore": ("C5DEF5", "Tooling, CI, housekeeping"),
    "pillar:security": ("B60205", "Well-Architected: security"),
    "pillar:reliability": ("D93F0B", "Well-Architected: reliability"),
    "pillar:performance": ("E99695", "Well-Architected: performance efficiency"),
    "pillar:cost": ("F9D0C4", "Well-Architected: cost optimisation"),
    "pillar:operations": ("BFD4F2", "Well-Architected: operational excellence"),
    "slice:S0": ("EDEDED", "Slice 0: Foundation"),
    "slice:S1": ("EDEDED", "Slice 1: Create project"),
    "slice:S2": ("EDEDED", "Slice 2: Read projects"),
    "slice:S3": ("EDEDED", "Slice 3: Operate"),
    "slice:S4": ("EDEDED", "Slice 4: Lifecycle"),
    "status:blocked": ("000000", "Cannot proceed; see the issue for what unblocks it"),
}

MILESTONES: dict[str, str] = {
    "S0 Foundation": "Deployed, monitored GET /health behind API Gateway.",
    "S1 Create project": "API-key holder can create a project: 201, or 409 if the name is taken.",
    "S2 Read projects": "Owners can fetch and list their projects.",
    "S3 Operate": "On-call can see health, correlate requests, get paged and roll back.",
    "S4 Lifecycle": "Delete, async provisioning skeleton, production environment.",
}


@dataclass
class Ticket:
    path: Path
    title: str
    labels: list[str]
    milestone: str
    status: str
    body: str


def run(cmd: list[str], *, dry_run: bool = False, mutating: bool = True) -> str:
    if dry_run and mutating:
        print("DRY:", " ".join(cmd))
        return ""
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()  # noqa: S603


def parse(path: Path) -> Ticket:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise SystemExit(f"{path}: missing front matter")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    labels = [label.strip() for label in meta["labels"].split(",") if label.strip()]
    slice_label = f"slice:{path.name.split('-')[0]}"
    if slice_label not in labels:
        labels.append(slice_label)
    return Ticket(
        path,
        meta["title"],
        labels,
        meta["milestone"],
        meta.get("status", "open"),
        m.group(2).strip(),
    )


def ensure_labels(repo: str, dry_run: bool) -> None:
    raw = run(
        ["gh", "label", "list", "--repo", repo, "--limit", "200", "--json", "name"], mutating=False
    )
    existing = {item["name"] for item in json.loads(raw or "[]")}
    for name, (color, desc) in LABELS.items():
        if name in existing:
            continue
        run(
            [
                "gh",
                "label",
                "create",
                name,
                "--repo",
                repo,
                "--color",
                color,
                "--description",
                desc,
            ],
            dry_run=dry_run,
        )
        print(f"label     + {name}")


def ensure_milestones(repo: str, dry_run: bool) -> None:
    raw = run(["gh", "api", f"repos/{repo}/milestones?state=all&per_page=100"], mutating=False)
    existing = {m["title"] for m in json.loads(raw or "[]")}
    for title, desc in MILESTONES.items():
        if title in existing:
            continue
        run(
            [
                "gh",
                "api",
                f"repos/{repo}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"description={desc}",
            ],
            dry_run=dry_run,
        )
        print(f"milestone + {title}")


def existing_issues(repo: str) -> dict[str, int]:
    raw = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "title,number",
        ],
        mutating=False,
    )
    return {i["title"]: i["number"] for i in json.loads(raw or "[]")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="owner/name (default: the current repo)")
    ap.add_argument("--done-sha", default=None, help="commit that implements `done` tickets")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = args.repo or run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], mutating=False
    )
    print(f"repo: {repo}")

    ensure_labels(repo, args.dry_run)
    ensure_milestones(repo, args.dry_run)
    known = existing_issues(repo)

    for path in TICKETS:
        t = parse(path)
        if t.title in known:
            print(f"issue     = #{known[t.title]} {t.title}")
            continue
        body_file = ROOT / "build" / "issue_bodies" / t.path.name
        body_file.parent.mkdir(parents=True, exist_ok=True)
        body_file.write_text(t.body + f"\n\n---\n_Seed: `docs/tickets/{t.path.name}`_\n")
        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            t.title,
            "--body-file",
            str(body_file),
            "--milestone",
            t.milestone,
        ]
        for label in t.labels:
            cmd += ["--label", label]
        url = run(cmd, dry_run=args.dry_run)
        number = int(url.rsplit("/", 1)[-1]) if url else -1
        print(f"issue     + #{number} {t.title}")
        if t.status == "done":
            note = (
                f"Implemented in {args.done_sha}."
                if args.done_sha
                else "Implemented in the initial commit."
            )
            if number > 0:
                run(
                    [
                        "gh",
                        "issue",
                        "close",
                        str(number),
                        "--repo",
                        repo,
                        "--comment",
                        note,
                        "--reason",
                        "completed",
                    ],
                    dry_run=args.dry_run,
                )
            print("            closed (done)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
