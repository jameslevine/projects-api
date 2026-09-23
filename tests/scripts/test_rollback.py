"""Tests for `scripts/rollback.sh` against a fake `aws` CLI, so no AWS access is needed.

The fake answers `lambda get-alias`, `lambda list-versions-by-function` and `lambda update-alias`
from canned files in `tmp_path` and appends every invocation to `calls.log`. `update-alias`
updates the canned alias so the script's confirmation re-read sees the change.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rollback.sh"

FAKE_AWS = r"""#!/usr/bin/env bash
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
printf '%s\n' "$*" >> "$dir/calls.log"
if [ -f "$dir/fail" ]; then
  echo "An error occurred (ResourceNotFoundException) when calling the $2 operation" >&2
  exit 254
fi
case "$1 $2" in
  "lambda get-alias")
    cat "$dir/alias.txt" ;;
  "lambda list-versions-by-function")
    cat "$dir/versions.txt" ;;
  "lambda update-alias")
    while [ $# -gt 1 ]; do
      if [ "$1" = "--function-version" ]; then printf '%s\n' "$2" > "$dir/alias.txt"; fi
      shift
    done
    printf '{"Name": "live", "FunctionVersion": "%s"}\n' "$(cat "$dir/alias.txt")" ;;
  *)
    echo "fake aws: unsupported command: $*" >&2
    exit 254 ;;
esac
"""

# Deliberately unsorted, with a two-digit version so numeric (not lexical) ordering is exercised
# and a "None" description as the CLI prints for a null field.
VERSIONS_TEXT = (
    "3\t2026-09-18T09:00:00.000+0000\tsha3\n"
    "12\t2026-09-22T10:00:00.000+0000\tsha12\n"
    "5\t2026-09-20T10:00:00.000+0000\tsha5\n"
    "4\t2026-09-19T09:30:00.000+0000\tNone\n"
)


@pytest.fixture
def fake_aws(tmp_path: Path) -> Path:
    aws = tmp_path / "aws"
    aws.write_text(FAKE_AWS)
    aws.chmod(0o755)
    (tmp_path / "alias.txt").write_text("5\n")
    (tmp_path / "versions.txt").write_text(VERSIONS_TEXT)
    return tmp_path


def run(fake: Path, *args: str, env_var: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "ENV"}  # conftest sets ENV=local
    env["AWS_CLI"] = str(fake / "aws")
    if env_var is not None:
        env["ENV"] = env_var
    return subprocess.run(  # noqa: S603 - fixed script path, test-controlled arguments
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def calls(fake: Path) -> list[str]:
    log = fake / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def update_calls(fake: Path) -> list[str]:
    return [c for c in calls(fake) if c.startswith("lambda update-alias")]


def alias_version(fake: Path) -> str:
    return (fake / "alias.txt").read_text().strip()


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)


def test_default_target_is_previous_version_and_yes_skips_the_prompt(fake_aws: Path) -> None:
    r = run(fake_aws, "--yes")
    assert r.returncode == 0, r.stderr
    assert update_calls(fake_aws) == [
        "lambda update-alias --function-name projects-api-dev --name live --function-version 4"
    ]
    assert alias_version(fake_aws) == "4"
    assert "Before: live -> 5" in r.stdout
    assert "After : live -> 4" in r.stdout
    assert "now points at version 4 (was 5)" in r.stdout
    assert "terraform apply" in r.stdout
    assert "make smoke" in r.stdout
    assert "12" in r.stdout, "the version table lists every published version"


def test_dry_run_prints_the_command_and_changes_nothing(fake_aws: Path) -> None:
    r = run(fake_aws, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert update_calls(fake_aws) == []
    assert alias_version(fake_aws) == "5"
    expected = "update-alias --function-name projects-api-dev --name live --function-version 4"
    assert expected in r.stdout
    assert "nothing changed" in r.stdout


def test_explicit_version_is_used(fake_aws: Path) -> None:
    r = run(fake_aws, "--version", "3", "--yes")
    assert r.returncode == 0, r.stderr
    assert update_calls(fake_aws) == [
        "lambda update-alias --function-name projects-api-dev --name live --function-version 3"
    ]
    assert alias_version(fake_aws) == "3"


def test_rolling_forward_warns_but_is_allowed(fake_aws: Path) -> None:
    r = run(fake_aws, "--version=12", "--yes")
    assert r.returncode == 0, r.stderr
    assert "rolls forward" in r.stdout
    assert alias_version(fake_aws) == "12"


def test_no_lower_version_exits_2_without_changes(fake_aws: Path) -> None:
    (fake_aws / "alias.txt").write_text("3\n")
    r = run(fake_aws, "--yes")
    assert r.returncode == 2
    assert "no earlier published version" in r.stderr
    assert update_calls(fake_aws) == []


def test_no_published_versions_exits_2(fake_aws: Path) -> None:
    (fake_aws / "versions.txt").write_text("")
    r = run(fake_aws, "--yes")
    assert r.returncode == 2
    assert "no published versions" in r.stderr
    assert update_calls(fake_aws) == []


@pytest.mark.parametrize("version", ["7", "5"])
def test_unpublished_or_current_explicit_version_exits_2(fake_aws: Path, version: str) -> None:
    r = run(fake_aws, "--version", version, "--yes")
    assert r.returncode == 2, r.stderr
    assert update_calls(fake_aws) == []


@pytest.mark.parametrize(
    "args",
    [("--bogus",), ("--env", "staging"), ("--version", "abc"), ("--version",)],
)
def test_usage_errors_exit_1_before_calling_aws(fake_aws: Path, args: tuple[str, ...]) -> None:
    r = run(fake_aws, *args)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "error:" in r.stderr
    assert calls(fake_aws) == []


def test_help_exits_0_without_calling_aws(fake_aws: Path) -> None:
    r = run(fake_aws, "--help")
    assert r.returncode == 0
    assert "--dry-run" in r.stdout
    assert calls(fake_aws) == []


def test_without_yes_and_no_tty_it_aborts_and_changes_nothing(fake_aws: Path) -> None:
    r = run(fake_aws)  # stdin is /dev/null, so the prompt reads EOF
    assert r.returncode == 1
    assert "aborted" in r.stdout
    assert update_calls(fake_aws) == []
    assert alias_version(fake_aws) == "5"


def test_env_selects_the_function_name(fake_aws: Path) -> None:
    r = run(fake_aws, "--env", "prod", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert calls(fake_aws)[0].startswith("lambda get-alias --function-name projects-api-prod ")

    (fake_aws / "calls.log").unlink()
    r = run(fake_aws, "--dry-run", env_var="prod")  # ENV variable, as `make rollback` sets it
    assert r.returncode == 0, r.stderr
    assert calls(fake_aws)[0].startswith("lambda get-alias --function-name projects-api-prod ")

    (fake_aws / "calls.log").unlink()
    r = run(fake_aws, "--function", "custom-fn", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert calls(fake_aws)[0].startswith("lambda get-alias --function-name custom-fn ")


def test_aws_failure_exits_3(fake_aws: Path) -> None:
    (fake_aws / "fail").touch()
    r = run(fake_aws, "--yes")
    assert r.returncode == 3
    assert "ResourceNotFoundException" in r.stderr
    assert update_calls(fake_aws) == []
