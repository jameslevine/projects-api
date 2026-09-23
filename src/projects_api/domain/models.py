"""Domain and API models."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from projects_api.domain.validation import validate_name


class ProjectType(StrEnum):
    """What the project will host."""

    AGENT = "agent"
    MCP = "mcp"
    WEB = "web"


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    PROVISIONING = "PROVISIONING"
    READY = "READY"
    FAILED = "FAILED"


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[
        str,
        Field(
            description="Human-chosen project name. 3 to 63 characters; letters, digits, "
            "spaces, hyphens and underscores. Globally unique, case-insensitive.",
            examples=["my-first-agent"],
        ),
    ]
    type: Annotated[ProjectType, Field(description="What the project will host.")]

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_name(value)


class Project(BaseModel):
    """A project record as stored and as returned to the caller."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    project_id: str = Field(alias="projectId")
    name: str
    type: ProjectType
    status: ProjectStatus
    owner_id: str = Field(alias="ownerId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def new(cls, *, name: str, type_: ProjectType, owner_id: str) -> "Project":
        now = datetime.now(UTC).replace(microsecond=0)
        return cls(
            project_id=f"prj_{uuid4().hex}",
            name=name,
            type=type_,
            status=ProjectStatus.CREATED,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )


class ProjectResponse(Project):
    """Public representation. Same shape as Project, serialised with camelCase keys."""
