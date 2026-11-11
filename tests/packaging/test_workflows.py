"""Workflow safety contracts; parse YAML 1.2-like strings with BaseLoader."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(filename: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(), Loader=yaml.BaseLoader
    )


def test_validation_only_runs_when_called_by_release():
    data = workflow("validate.yml")
    assert set(data["on"]) == {"workflow_call"}
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["catalog"]["steps"][0]["with"] == {
        "category": "integration",
        "comment": "false",
    }
    catalog = data["jobs"]["catalog"]["steps"][0]
    assert catalog["env"]["REPOSITORY_REF"] == "${{ inputs.ref || github.sha }}"
    for job in data["jobs"].values():
        assert "timeout-minutes" in job
        for step in job.get("steps", []):
            assert step.get("continue-on-error", "false") == "false"
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
                assert step["with"]["ref"] == "${{ inputs.ref || github.sha }}"


def test_release_validates_before_build_and_limits_write_permissions():
    data = workflow("release.yml")
    assert data["permissions"] == {"contents": "read"}
    assert data["on"]["workflow_dispatch"]["inputs"]["tag"]["required"] == "true"
    jobs = data["jobs"]
    assert jobs["validate"]["needs"] == "source"
    assert jobs["validate"]["uses"] == "./.github/workflows/validate.yml"
    assert jobs["validate"]["with"]["ref"] == "${{ needs.source.outputs.commit }}"
    assert set(jobs["build"]["needs"]) == {"source", "validate"}
    assert set(jobs["publish"]["needs"]) == {"source", "build"}
    assert jobs["publish"]["permissions"] == {"contents": "write"}
    assert all(
        job.get("permissions", {"contents": "read"}) == {"contents": "read"}
        for name, job in jobs.items()
        if name != "publish"
    )
    text = (ROOT / ".github/workflows/release.yml").read_text()
    assert "--clobber" not in text
    assert 'git", "commit' not in text
    assert "FORCE_OVERWRITE" not in text


def test_external_actions_are_sha_pinned():
    for filename in ("validate.yml", "release.yml"):
        data = workflow(filename)
        for job in data["jobs"].values():
            for step in job.get("steps", []):
                if uses := step.get("uses"):
                    assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", uses), uses
