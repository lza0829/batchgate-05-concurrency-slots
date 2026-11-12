from pydantic import BaseModel, Field

from app.engines.slots import MAX_CONCURRENCY, MIN_CONCURRENCY


class MaxAttemptsBody(BaseModel):
    max_attempts: int = Field(ge=1, le=10)


class OrchestrationRunBody(BaseModel):
    """Optional per-run slot override; omitted fields fall back to saved settings."""

    concurrency_limit: int | None = Field(
        default=None, ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY
    )
    slot_policy: str | None = Field(default=None, pattern="^(wait|skip)$")
