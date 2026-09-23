"""Domain exceptions. The API layer maps these to HTTP problem responses."""


class DomainError(Exception):
    """Base class for domain-level failures."""


class ProjectNameTakenError(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"A project named '{name}' already exists.")
        self.name = name


class ProjectNotFoundError(DomainError):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project '{project_id}' was not found.")
        self.project_id = project_id
