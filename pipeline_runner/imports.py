"""Resolution of Bitbucket "shared pipelines" imports.

A pipeline can be replaced by an import reference instead of a step list. Two forms exist:

* ``import: <pipeline-name>@<import-source-slug>`` — the import source is declared under
  ``definitions.imports`` and, when it points to a file inside the same repository, can be
  resolved locally (the case handled here).
* ``import: <repo>:<branch>:<pipeline-name>`` — the definition lives in another repository at a
  given branch; this can't be resolved locally and raises ``UnsupportedPipelineImportError``.

Resolution is lazy: only the pipeline actually being run (and any it triggers) is resolved, so a
partial checkout or an unrelated missing sibling component doesn't prevent listing or running.
"""

import os
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import ImportResolutionError, UnsupportedPipelineImportError
from .models import (
    Definitions,
    Image,
    ImageType,
    ParallelStep,
    Pipeline,
    PipelineImport,
    PipelineSpec,
    StageWrapper,
    StepWrapper,
)


def resolve_pipeline_import(
    imp: PipelineImport,
    spec: PipelineSpec,
    repo_root: str,
    *,
    pipeline_name: str,
) -> Pipeline:
    """Resolve a local shared-pipeline import into a concrete :class:`Pipeline`.

    ``pipeline_name`` is only used for error messages (e.g. ``custom.br-root``).
    Raises ``UnsupportedPipelineImportError`` for cross-repo imports and ``ImportResolutionError``
    when a local import can't be resolved (unknown source, missing file, or missing pipeline).
    """
    parsed = _split_local_source(imp.source)
    if parsed is None:
        # Cross-repo "repo:branch:pipeline" form (or otherwise unrecognized) — not resolvable here.
        raise UnsupportedPipelineImportError(pipeline_name, imp.source)

    name, slug = parsed

    imports_map = spec.definitions.imports
    if slug not in imports_map:
        raise ImportResolutionError(
            pipeline_name,
            imp.source,
            f"import source '{slug}' is not declared under definitions.imports",
        )

    rel_path = imports_map[slug]
    if ":" in rel_path:
        # The import source itself points at another repo (repo:branch:file).
        raise UnsupportedPipelineImportError(pipeline_name, imp.source)

    file_path = os.path.join(repo_root, rel_path)
    if not os.path.isfile(file_path):
        raise ImportResolutionError(pipeline_name, imp.source, f"file not found: {file_path}")

    with open(file_path) as f:
        data = yaml.safe_load(f) or {}

    shared_pipelines = (data.get("definitions") or {}).get("pipelines") or {}
    if name not in shared_pipelines:
        available = ", ".join(sorted(shared_pipelines)) or "none"
        raise ImportResolutionError(
            pipeline_name,
            imp.source,
            f"pipeline '{name}' not found in {rel_path} (available: {available})",
        )

    try:
        pipeline = Pipeline.model_validate(shared_pipelines[name])
    except ValidationError as e:
        raise ImportResolutionError(pipeline_name, imp.source, str(e)) from e

    # Bitbucket takes global options (image) and definitions (caches, services) from the exporting
    # file, not the importing one. Apply the exporting image to steps that don't set their own, and
    # make the exporting caches/services available so steps referencing them resolve.
    exporting_image = data.get("image")
    if exporting_image is not None:
        _apply_default_image(pipeline, exporting_image)

    _merge_definitions(spec, data.get("definitions") or {})

    return pipeline


def _split_local_source(source: str) -> tuple[str, str] | None:
    """Return ``(pipeline_name, import_source_slug)`` for a local ``name@slug`` import, else None."""
    name, sep, slug = source.partition("@")
    if sep and name and slug:
        return name, slug

    return None


def _apply_default_image(pipeline: Pipeline, image_data: ImageType) -> None:
    image = _coerce_image(image_data)
    if image is None:
        return

    for element in pipeline.get_steps():
        _apply_default_image_to_element(element, image)


def _apply_default_image_to_element(
    element: StepWrapper | ParallelStep | StageWrapper,
    image: Image,
) -> None:
    if isinstance(element, StepWrapper):
        if element.step.image is None and not element.step.is_pipeline_step:
            element.step.image = image
    elif isinstance(element, ParallelStep):
        for step_wrapper in element:
            if step_wrapper.step.image is None and not step_wrapper.step.is_pipeline_step:
                step_wrapper.step.image = image
    elif isinstance(element, StageWrapper):
        for step in element.stage.steps:
            _apply_default_image_to_element(step, image)


def _coerce_image(image_data: ImageType) -> Image | None:
    if image_data is None:
        return None

    if isinstance(image_data, Image):
        return image_data

    if isinstance(image_data, str):
        return Image(name=image_data)

    return Image.model_validate(image_data)


def _merge_definitions(spec: PipelineSpec, raw_definitions: dict[str, Any]) -> None:
    if not raw_definitions:
        return

    exporting = Definitions.model_validate(raw_definitions)

    for name, cache in exporting.caches.items():
        spec.definitions.caches.setdefault(name, cache)

    for name, service in exporting.services.items():
        spec.definitions.services.setdefault(name, service)
