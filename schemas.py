"""Validated data models for Acme AI governance assessments."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PolicyId = Literal[
    "AI-001",
    "AI-002",
    "AI-003",
    "AI-004",
    "AI-005",
    "AI-006",
    "AI-007",
    "AI-008",
]

EXPECTED_POLICY_IDS = frozenset(
    {
        "AI-001",
        "AI-002",
        "AI-003",
        "AI-004",
        "AI-005",
        "AI-006",
        "AI-007",
        "AI-008",
    }
)


class StrictModel(BaseModel):
    """Shared validation settings for assessment models."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class FindingStatus(str, Enum):
    SATISFIED = "satisfied"
    GAP_IDENTIFIED = "gap_identified"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Finding(StrictModel):
    policy_id: PolicyId
    status: FindingStatus
    control_evidence: Literal[
        "present",
        "explicitly_absent_or_inadequate",
        "unknown",
        "explicitly_not_applicable",
    ] = Field(
        description=(
            "What the scenario explicitly establishes about the required "
            "control. Risk factors and silence about controls mean unknown. "
            "Use explicitly_absent_or_inadequate only when the scenario "
            "directly describes a missing or inadequate control."
        )
    )
    evidence_quotes: list[str] = Field(
        description=(
            "Exact excerpts from the submitted scenario. "
            "Use an empty list when supporting evidence is missing."
        )
    )
    rationale: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)


class FollowUpQuestion(StrictModel):
    policy_id: PolicyId
    question: str = Field(min_length=1)


class Assessment(StrictModel):
    summary: str = Field(min_length=1)
    risk_level: RiskLevel
    risk_rationale: str = Field(min_length=1)
    additional_review_recommended: bool
    findings: list[Finding] = Field(min_length=8, max_length=8)
    follow_up_questions: list[FollowUpQuestion]

    @model_validator(mode="after")
    def validate_policy_coverage(self) -> "Assessment":
        """Require exactly one finding for each Acme policy."""
        actual_ids = {finding.policy_id for finding in self.findings}

        if actual_ids != EXPECTED_POLICY_IDS:
            missing_ids = sorted(EXPECTED_POLICY_IDS - actual_ids)
            raise ValueError(
                "Provide exactly one finding per Acme policy. "
                f"Missing policies: {', '.join(missing_ids)}."
            )

        return self