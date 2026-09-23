"""Provisioner implementations, one per `ProjectType`.

These are placeholders: each returns success without creating any resources, so the pipeline
(stream -> handler -> status transitions) can be exercised end to end with no side effects.
What a project of each type provisions is designed in docs/adr/0005-per-type-provisioning.md;
the real implementations replace the stubs behind the same `Provisioner` protocol.
"""

from dataclasses import dataclass, field
from typing import Protocol

from projects_api.domain.models import ProjectType


@dataclass(frozen=True)
class ProvisionRequest:
    """What the provisioner needs to know about the project; taken from the stream image."""

    project_id: str
    name: str
    type: ProjectType
    owner_id: str


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of a successful provisioning run. Failure is signalled by raising."""

    endpoint: str | None = None
    details: dict[str, str] = field(default_factory=dict)


class Provisioner(Protocol):
    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        """Create the resources for `project`. Raise on failure; the handler marks it FAILED."""
        ...


class AgentProvisioner:
    """Placeholder for the ADR 0005 design: succeeds without creating anything."""

    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        return ProvisionResult()


class McpProvisioner:
    """Placeholder for the ADR 0005 design: succeeds without creating anything."""

    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        return ProvisionResult()


class WebProvisioner:
    """Placeholder for the ADR 0005 design: succeeds without creating anything."""

    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        return ProvisionResult()


PROVISIONERS: dict[ProjectType, Provisioner] = {
    ProjectType.AGENT: AgentProvisioner(),
    ProjectType.MCP: McpProvisioner(),
    ProjectType.WEB: WebProvisioner(),
}
