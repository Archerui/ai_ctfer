from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter

from .actions import extract_json_object


class CandidateValidationResult(BaseModel):
    verdict: Literal["trusted", "uncertain", "decoy"]
    confidence: int = Field(ge=0, le=100)
    rationale: str = ""
    risk: str = ""


VALIDATION_ADAPTER = TypeAdapter(CandidateValidationResult)


def parse_candidate_validation(text: str) -> CandidateValidationResult:
    data = json.loads(extract_json_object(text))
    return VALIDATION_ADAPTER.validate_python(data)


def candidate_validation_schema_hint() -> str:
    return (
        'Return exactly one JSON object: '
        '{"verdict":"trusted","confidence":0-100,"rationale":"...",'
        '"risk":"..."}. verdict must be one of trusted, uncertain, decoy.'
    )
