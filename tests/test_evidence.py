import pytest

from agent import AssessmentError, validate_evidence
from schemas import Assessment, EXPECTED_POLICY_IDS
from pydantic import ValidationError


def make_assessment(quote: str) -> Assessment:
    return Assessment.model_validate(
        {
            "summary": "Sensitive data requires clarification of controls.",
            "risk_level": "medium",
            "risk_rationale": "Data protections are not described.",
            "additional_review_recommended": False,
            "findings": [
                {
                    "policy_id": policy_id,
                    "status": "insufficient_information",
                    "control_evidence": "unknown",
                    "evidence_quotes": (
                        [quote] if policy_id == "AI-002" else []
                    ),
                    "rationale": "The necessary controls are not described.",
                    "recommended_action": "Confirm and document the controls.",
                }
                for policy_id in sorted(EXPECTED_POLICY_IDS)
            ],
            "follow_up_questions": [
                {
                    "policy_id": policy_id,
                    "question": "What controls satisfy this requirement?",
                }
                for policy_id in sorted(EXPECTED_POLICY_IDS)
            ],
        }
    )


def test_evidence_accepts_whitespace_differences():
    scenario = "The system processes customer names,\n    account information."
    assessment = make_assessment("customer names, account information.")

    validate_evidence(assessment, scenario, set(EXPECTED_POLICY_IDS))


@pytest.mark.parametrize(
    "quote",
    [
        "customer names and account information.",
        "The system encrypts account information.",
        "   ",
    ],
)
def test_evidence_rejects_changed_or_empty_quotes(quote):
    scenario = "The system processes customer names,\n    account information."
    assessment = make_assessment(quote)

    with pytest.raises(AssessmentError, match="evidence"):
        validate_evidence(assessment, scenario, set(EXPECTED_POLICY_IDS))


def test_unknown_control_cannot_be_reported_as_confirmed_gap():
    assessment = make_assessment("customer information")
    finding = next(
        item for item in assessment.findings
        if item.policy_id == "AI-003"
    )
    finding.status = type(finding.status).GAP_IDENTIFIED

    with pytest.raises(AssessmentError, match="status conflicts"):
        validate_evidence(
            assessment,
            "The system processes customer information.",
            set(EXPECTED_POLICY_IDS),
        )


def test_unretrieved_policy_is_rejected():
    assessment = make_assessment("customer information")
    retrieved_ids = set(EXPECTED_POLICY_IDS) - {"AI-002"}

    with pytest.raises(AssessmentError, match="unretrieved policy"):
        validate_evidence(
            assessment,
            "The system processes customer information.",
            retrieved_ids,
        )


def test_unknown_control_requires_follow_up_question():
    assessment = make_assessment("customer information")
    assessment.follow_up_questions = [
        question
        for question in assessment.follow_up_questions
        if question.policy_id != "AI-004"
    ]

    with pytest.raises(AssessmentError, match="AI-004: missing"):
        validate_evidence(
            assessment,
            "The system processes customer information.",
            set(EXPECTED_POLICY_IDS),
        )


def test_confirmed_gap_requires_evidence():
    assessment = make_assessment("customer information")
    finding = next(
        item for item in assessment.findings
        if item.policy_id == "AI-003"
    )
    finding.status = type(finding.status).GAP_IDENTIFIED
    finding.control_evidence = "explicitly_absent_or_inadequate"
    finding.evidence_quotes = []

    with pytest.raises(AssessmentError, match="requires scenario evidence"):
        validate_evidence(
            assessment,
            "The system processes customer information.",
            set(EXPECTED_POLICY_IDS),
        )


def test_high_risk_requires_additional_review():
    assessment = make_assessment("customer information")
    assessment.risk_level = type(assessment.risk_level).HIGH
    assessment.additional_review_recommended = False

    with pytest.raises(AssessmentError, match="require additional review"):
        validate_evidence(
            assessment,
            "The system processes customer information.",
            set(EXPECTED_POLICY_IDS),
        )


def test_duplicate_policy_cannot_replace_another_policy():
    assessment = make_assessment("customer information")
    payload = assessment.model_dump(mode="json")
    payload["findings"][-1]["policy_id"] = "AI-001"

    with pytest.raises(ValidationError, match="exactly one finding"):
        Assessment.model_validate(payload)