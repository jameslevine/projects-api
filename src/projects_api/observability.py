"""Powertools singletons: structured logging, tracing and custom metrics.

One instance each, shared across the Lambda execution environment so that
correlation ids and cold-start flags are handled consistently.
"""

from aws_lambda_powertools import Logger, Metrics, Tracer

from projects_api.config import get_settings

_settings = get_settings()

logger = Logger(service=_settings.service_name, level=_settings.log_level)
tracer = Tracer(service=_settings.service_name, disabled=_settings.is_local)
metrics = Metrics(namespace="ProjectsApi", service=_settings.service_name)
