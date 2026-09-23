"""Provisioner Lambda: consumes the projects table stream and drives project status transitions.

Shares configuration, observability singletons, domain enums and key helpers with
`projects_api`; both packages ship in the same deployment zip.
"""
