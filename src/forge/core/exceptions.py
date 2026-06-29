class ForgeError(Exception):
    """Base exception for all forge runtime errors."""


class ConfigurationError(ForgeError):
    """Raised when configuration is missing, invalid, or misconfigured."""


class RuntimeNotInitializedError(ForgeError):
    """Raised when an operation requires an initialized runtime but it is not."""


class ModuleError(ForgeError):
    """Base exception for module-related errors."""


class ModuleNotFoundError(ModuleError):
    """Raised when a requested module is not registered."""


class ModuleRegistrationError(ModuleError):
    """Raised when module registration fails (e.g., duplicate registration)."""


class CircularDependencyError(ModuleError):
    """Raised when a circular dependency is detected between modules."""


class ModuleStateError(ModuleError):
    """Raised when a module operation is invalid for its current lifecycle state."""


class EventError(ForgeError):
    """Raised when an event bus operation fails."""


class HealthCheckError(ForgeError):
    """Raised when a health check fails critically."""


class JobError(ForgeError):
    """Base exception for job-related errors."""


class JobNotFoundError(JobError):
    """Raised when a job is not found."""


class JobExecutionError(JobError):
    """Raised when a job execution fails."""
