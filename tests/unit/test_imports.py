from pathlib import Path
from textwrap import dedent

import pytest

from pipeline_runner.errors import ImportResolutionError, UnsupportedPipelineImportError
from pipeline_runner.imports import resolve_pipeline_import
from pipeline_runner.models import Pipeline, PipelineImport, PipelineSpec, StepWrapper


def _spec(imports: dict[str, str]) -> PipelineSpec:
    return PipelineSpec.model_validate(
        {
            "definitions": {"imports": imports},
            "pipelines": {"custom": {"placeholder": [{"step": {"script": ["true"]}}]}},
        }
    )


def _import(source: str) -> PipelineImport:
    return PipelineImport.model_validate({"import": source})


def test_resolve_local_import_returns_pipeline(tmp_path: Path) -> None:
    (tmp_path / "shared.yml").write_text(
        dedent("""
            definitions:
              pipelines:
                mypipe:
                  - step:
                      name: hello
                      image: alpine
                      script:
                        - echo hi
        """)
    )

    spec = _spec({"src": "shared.yml"})
    resolved = resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")

    assert isinstance(resolved, Pipeline)
    steps = resolved.get_steps()
    assert isinstance(steps[0], StepWrapper)
    assert steps[0].step.name == "hello"


def test_resolve_applies_in_file_anchors(tmp_path: Path) -> None:
    (tmp_path / "shared.yml").write_text(
        dedent("""
            definitions:
              pipelines:
                mypipe:
                  - step:
                      name: a
                      image: alpine
                      script:
                        - echo a
                      artifacts: &arts
                        - out/report.txt
                  - step:
                      name: b
                      image: alpine
                      script:
                        - echo b
                      artifacts: *arts
        """)
    )

    spec = _spec({"src": "shared.yml"})
    resolved = resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")

    steps = resolved.get_steps()
    assert isinstance(steps[0], StepWrapper)
    assert isinstance(steps[1], StepWrapper)
    # The aliased artifacts list is resolved by the YAML loader on both steps.
    assert steps[0].step.artifacts.paths == ["out/report.txt"]
    assert steps[1].step.artifacts.paths == ["out/report.txt"]


def test_resolve_applies_exporting_image_to_steps_without_one(tmp_path: Path) -> None:
    (tmp_path / "shared.yml").write_text(
        dedent("""
            image: debian:trixie
            definitions:
              pipelines:
                mypipe:
                  - step:
                      name: inherits
                      script:
                        - echo a
                  - step:
                      name: keeps-own
                      image: alpine
                      script:
                        - echo b
        """)
    )

    spec = _spec({"src": "shared.yml"})
    resolved = resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")

    steps = resolved.get_steps()
    assert isinstance(steps[0], StepWrapper)
    assert isinstance(steps[1], StepWrapper)
    assert steps[0].step.image is not None
    assert steps[0].step.image.name == "debian:trixie"
    assert steps[1].step.image is not None
    assert steps[1].step.image.name == "alpine"


def test_resolve_merges_exporting_definitions(tmp_path: Path) -> None:
    (tmp_path / "shared.yml").write_text(
        dedent("""
            definitions:
              caches:
                mycache: ~/.cache/mine
              services:
                myservice:
                  image: postgres:15
              pipelines:
                mypipe:
                  - step:
                      name: a
                      image: alpine
                      caches:
                        - mycache
                      services:
                        - myservice
                      script:
                        - echo a
        """)
    )

    spec = _spec({"src": "shared.yml"})
    resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")

    assert "mycache" in spec.definitions.caches
    assert "myservice" in spec.definitions.services


def test_resolve_unknown_import_source_raises(tmp_path: Path) -> None:
    spec = _spec({"known": "shared.yml"})

    with pytest.raises(ImportResolutionError, match="is not declared under definitions"):
        resolve_pipeline_import(_import("mypipe@unknown"), spec, str(tmp_path), pipeline_name="custom.x")


def test_resolve_missing_file_raises(tmp_path: Path) -> None:
    spec = _spec({"src": "does-not-exist.yml"})

    with pytest.raises(ImportResolutionError, match="file not found"):
        resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")


def test_resolve_missing_pipeline_in_file_raises(tmp_path: Path) -> None:
    (tmp_path / "shared.yml").write_text(
        dedent("""
            definitions:
              pipelines:
                other:
                  - step:
                      image: alpine
                      script:
                        - echo a
        """)
    )

    spec = _spec({"src": "shared.yml"})

    with pytest.raises(ImportResolutionError, match="pipeline 'mypipe' not found"):
        resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")


def test_resolve_cross_repo_import_is_unsupported(tmp_path: Path) -> None:
    spec = _spec({})

    with pytest.raises(UnsupportedPipelineImportError, match="other-repo:main:pipeline"):
        resolve_pipeline_import(
            _import("other-repo:main:pipeline"), spec, str(tmp_path), pipeline_name="custom.x"
        )


def test_resolve_import_source_pointing_at_other_repo_is_unsupported(tmp_path: Path) -> None:
    # The import source slug resolves, but points at another repo (repo:branch:file), not a local path.
    spec = _spec({"src": "other-repo:main:.bitbucket/shared.yml"})

    with pytest.raises(UnsupportedPipelineImportError, match="mypipe@src"):
        resolve_pipeline_import(_import("mypipe@src"), spec, str(tmp_path), pipeline_name="custom.x")
