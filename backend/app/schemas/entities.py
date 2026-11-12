from pydantic import BaseModel, Field


class MaxAttemptsBody(BaseModel):
    max_attempts: int = Field(ge=1, le=10)
