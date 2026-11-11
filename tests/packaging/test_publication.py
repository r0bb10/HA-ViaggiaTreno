"""Mock all GitHub operations; these tests never publish anything."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import publish_release
from scripts.build_release import build_release


@pytest.mark.parametrize(
    "tag,releases,expected",
    [
        ("1.2.3", [], True),
        ("1.2.3rc1", [], False),
        (
            "1.2.3",
            [{"tagName": "2.0.0", "isDraft": False, "isPrerelease": False}],
            False,
        ),
        (
            "1.2.3",
            [{"tagName": "1.0.0", "isDraft": False, "isPrerelease": False}],
            True,
        ),
        (
            "1.2.3",
            [{"tagName": "legacy", "isDraft": False, "isPrerelease": False}],
            False,
        ),
    ],
)
def test_latest_selection(tag: str, releases: list[dict], expected: bool) -> None:
    assert publish_release.should_mark_latest(tag, releases) is expected


def test_publishes_validated_asset_via_draft(
    release_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = build_release(release_repository, release_repository / "dist", "1.2.3")
    mock = Mock(
        side_effect=[
            json.dumps({"object": {"type": "commit", "sha": "a" * 40}}),
            "[]",
            "",
            "",
        ]
    )
    monkeypatch.setattr(publish_release, "gh", mock)
    publish_release.publish("owner/repository", "1.2.3", "a" * 40, asset)
    create, edit = mock.call_args_list[-2:]
    assert create.args[:3] == ("release", "create", "1.2.3")
    assert "--verify-tag" in create.args
    assert "--draft" in create.args
    assert "--clobber" not in create.args
    assert "--draft=false" in edit.args
    assert "--latest=true" in edit.args


@pytest.mark.parametrize("existing", [False, True])
def test_refuses_moved_tag_or_existing_release(
    release_repository: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    asset = build_release(release_repository, release_repository / "dist", "1.2.3")
    responses = [
        json.dumps(
            {"object": {"type": "commit", "sha": ("a" if existing else "b") * 40}}
        )
    ]
    if existing:
        responses.append(
            json.dumps(
                [
                    {
                        "tagName": "1.2.3",
                        "isDraft": False,
                        "isPrerelease": False,
                    }
                ]
            )
        )
    mock = Mock(side_effect=responses)
    monkeypatch.setattr(publish_release, "gh", mock)
    with pytest.raises(ValueError):
        publish_release.publish("owner/repository", "1.2.3", "a" * 40, asset)
    assert not any(
        call.args[:2] == ("release", "create") for call in mock.call_args_list
    )


def test_annotated_tag_is_resolved_without_branch_ambiguity(
    release_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = build_release(release_repository, release_repository / "dist", "1.2.3")
    mock = Mock(
        side_effect=[
            json.dumps({"object": {"type": "tag", "sha": "b" * 40}}),
            json.dumps({"object": {"type": "commit", "sha": "a" * 40}}),
            "[]",
            "",
            "",
        ]
    )
    monkeypatch.setattr(publish_release, "gh", mock)
    publish_release.publish("owner/repository", "1.2.3", "a" * 40, asset)
    assert mock.call_args_list[0].args == (
        "api",
        "repos/owner/repository/git/ref/tags/1.2.3",
    )
    assert mock.call_args_list[1].args == (
        "api",
        "repos/owner/repository/git/tags/" + "b" * 40,
    )
