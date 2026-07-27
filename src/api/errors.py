# ~/src/api/errors.py
# Standardized error envelope for every HTTPException raised across the API.
#
# Every error response uses `detail = {"error": <message>, "retry_after": <seconds|null>}`,
# so a single client-side handler can always read `response.json()["detail"]["error"]`
# (and optionally `["retry_after"]`) regardless of which layer raised the exception.

from fastapi import HTTPException


def api_error(status_code: int, error: str, retry_after: float | None = None) -> HTTPException:
    """Build an HTTPException using the API's standardized error envelope."""
    return HTTPException(status_code=status_code, detail={"error": error, "retry_after": retry_after})
