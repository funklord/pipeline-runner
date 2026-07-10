from textwrap import indent

from click.exceptions import UsageError


class PipelinesFileNotFoundError(UsageError, ValueError):
    def __init__(self, file: str) -> None:
        super().__init__(f"Pipelines file not found: {file}")


class PipelinesFileParseError(UsageError):
    def __init__(self, error: str) -> None:
        super().__init__(f"Error parsing pipelines file:\n{error}")


class PipelinesFileValidationError(UsageError):
    def __init__(self, error: str) -> None:
        super().__init__(f"Invalid pipelines file:\n{indent(error, '  ')}")


class InvalidPipelineError(UsageError, ValueError):
    def __init__(self, pipeline_name: str, valid_pipelines: list[str] | None = None) -> None:
        msg = f"Invalid pipeline: {pipeline_name}"

        if valid_pipelines:
            valid_pipelines_str = "\n\t".join(valid_pipelines)
            msg += f"\nAvailable pipelines:\n\t{valid_pipelines_str}"

        super().__init__(msg)


class InvalidServiceError(UsageError, ValueError):
    def __init__(self, service_name: str) -> None:
        super().__init__(f"Invalid service: {service_name}")


class PipelineCycleError(UsageError, ValueError):
    def __init__(self, chain: list[str]) -> None:
        super().__init__(f"Pipeline trigger cycle detected: {' -> '.join(chain)}")


class UnsupportedPipelineImportError(UsageError, ValueError):
    def __init__(self, pipeline_name: str, source: str) -> None:
        super().__init__(
            f"Pipeline '{pipeline_name}' is imported from a shared configuration ('{source}'). "
            "pipeline-runner can't resolve shared pipeline imports locally, so imported pipelines "
            "can be listed but not run."
        )


class ImportResolutionError(UsageError, ValueError):
    def __init__(self, pipeline_name: str, source: str, reason: str) -> None:
        super().__init__(f"Could not resolve import for pipeline '{pipeline_name}' ('{source}'): {reason}")


class NegativeIntegerError(ValueError):
    def __init__(self) -> None:
        super().__init__("value must be a positive integer")


class InvalidCacheKeyError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f'Cache "{name}": Cache key files could not be found')


class ArtifactManagementError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class InvalidOutputVariablesError(UsageError):
    def __init__(self, invalid_variable: str) -> None:
        super().__init__(f"Invalid variable format: {invalid_variable}")


class UndefinedOutputVariablesError(UsageError):
    def __init__(self, invalid_variables: set[str]) -> None:
        if len(invalid_variables) == 1:
            var = invalid_variables.pop()
            msg = f"The {var} variable is not defined in the output variables. Define this output variable."
        else:
            var_names = ", ".join(invalid_variables)
            msg = f"The {var_names} variables are not defined in the output variables. Define these output variables."

        super().__init__(msg)
