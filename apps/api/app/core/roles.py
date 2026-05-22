"""
Role-based access control dependency for Pentecostal Live API.

Usage:
    from app.core.roles import require_roles

    @router.post("/some-endpoint")
    def my_endpoint(
        context: CurrentContext = Depends(get_current_context),
        _: None = Depends(require_roles("owner", "admin")),
    ):
        ...

Role hierarchy (most → least privileged):
    owner    — full org access
    admin    — manage streams, keys, users, settings
    producer — start/stop streams, switch scenes
    viewer   — read-only
"""

from fastapi import Depends, HTTPException, status

from app.deps import CurrentContext, get_current_context


def require_roles(*allowed_roles: str):
    """
    Returns a FastAPI dependency that enforces role membership.
    Raises HTTP 403 if the current user's role is not in allowed_roles.
    """

    def _check(context: CurrentContext = Depends(get_current_context)) -> None:
        if context.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{context.role.name}' is not permitted to perform this action. "
                    f"Required: {', '.join(allowed_roles)}."
                ),
            )

    return _check
