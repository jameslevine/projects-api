from fastapi import APIRouter

from projects_api import __version__

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
