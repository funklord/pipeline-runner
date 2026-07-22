from unittest.mock import Mock

import pytest

from pipeline_runner.models import CloneSettings
from pipeline_runner.repository import RepositoryCloner


def _make_cloner(branch: str | None) -> RepositoryCloner:
    ctx = Mock()
    ctx.pipeline_ctx.repository.get_current_branch.return_value = branch
    ctx.step.clone_settings = CloneSettings.empty()
    ctx.pipeline_ctx.clone_settings = CloneSettings()

    return RepositoryCloner(
        ctx,
        environment={},
        user=None,
        parent_container_name="some-container",
        data_volume_name="some-volume",
        output_logger=Mock(),
    )


@pytest.mark.parametrize(
    ("branch", "should_contain_branch_flag"),
    [("main", True), (None, False)],
)
def test_get_clone_command_branch_flag(branch: str | None, *, should_contain_branch_flag: bool) -> None:
    cloner = _make_cloner(branch)

    command = cloner._get_clone_command("file:///some/origin")

    assert ("--branch=" in command) is should_contain_branch_flag
    if branch:
        assert f"--branch='{branch}'" in command


def test_get_clone_command_still_applies_depth_when_branch_is_unknown() -> None:
    cloner = _make_cloner(None)

    command = cloner._get_clone_command("file:///some/origin")

    assert "--depth 50" in command
    assert "git clone --depth 50 file:///some/origin" in command
