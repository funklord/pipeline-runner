from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from pipeline_runner.config import config
from pipeline_runner.models import CloneSettings
from pipeline_runner.repository import RepositoryCloner


def _make_cloner(branch: str | None = None, depth: str | int | None = 50) -> RepositoryCloner:
    ctx = Mock()
    ctx.pipeline_ctx.repository.get_current_branch.return_value = branch
    ctx.step.clone_settings = CloneSettings.empty()
    ctx.pipeline_ctx.clone_settings = CloneSettings(depth=depth)

    return RepositoryCloner(
        ctx,
        environment={},
        user=None,
        parent_container_name="some-container",
        data_volume_name="some-volume",
        output_logger=Mock(),
    )


@pytest.mark.parametrize("branch", ["main", None])
def test_get_clone_command_no_longer_needs_branch_or_depth(branch: str | None) -> None:
    # Branch/depth selection happens once, on the host, when the disposable copy handed to the
    # container is created (Repository.create_local_clone) - nothing left to restrict here.
    cloner = _make_cloner(branch)

    command = cloner._get_clone_command("/some/origin")

    assert command == "GIT_LFS_SKIP_SMUDGE=1 git clone /some/origin $BUILD_DIR"


def test_upload_repository_creates_a_local_clone_and_uploads_it(mocker: MockerFixture) -> None:
    cloner = _make_cloner(branch="main", depth=7)

    # create_local_clone normally shells out to git; not exercising that here, just checking it's
    # called with the resolved branch/depth and that the result gets archived to the right place.
    cloner._repository.create_local_clone = Mock()
    mocker.patch("pipeline_runner.repository.tarfile.open")

    runner = Mock()
    runner.put_archive.return_value = True

    cloner._upload_repository(runner)

    _args, kwargs = cloner._repository.create_local_clone.call_args
    assert kwargs == {"branch": "main", "depth": 7}

    (upload_path, _data), _ = runner.put_archive.call_args
    assert upload_path == config.remote_workspace_dir


def test_upload_repository_raises_if_the_upload_fails(mocker: MockerFixture) -> None:
    cloner = _make_cloner()

    cloner._repository.create_local_clone = Mock()
    mocker.patch("pipeline_runner.repository.tarfile.open")

    runner = Mock()
    runner.put_archive.return_value = False

    with pytest.raises(Exception, match="Error uploading repository"):
        cloner._upload_repository(runner)
