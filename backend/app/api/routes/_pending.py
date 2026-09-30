"""Shared helper for endpoints that exist but await the dataset."""

from fastapi import HTTPException, status

PENDING_RESPONSES = {501: {"description": "Pending dataset (Phase 2)"}}


def pending(feature: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{feature} is not available yet: it is implemented after the "
               "official dataset is provided and mapped.",
    )
