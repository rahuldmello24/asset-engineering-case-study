"""Bounded agent workflow for evidence-backed AI assessments."""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

from policy_tools import PolicyRequest, get_policies
from prompts import ASSESSMENT_INSTRUCTIONS
from schemas import Assessment, EXPECTED_POLICY_IDS, FindingStatus, RiskLevel


MAX_SCENARIO_LENGTH = 12_000
MAX_RETRIEVAL_ROUNDS = 3

POLICY_TOOL = {
    "type": "function",
    "name": "get_policies",
    "description": (
        "Retrieve Acme AI governance requirements by ID. "
        "Pass an empty policy_ids list to retrieve all eight requirements."
    ),
    "parameters": PolicyRequest.model_json_schema(),
    "strict": True,
}


class AssessmentError(Exception):
    """An assessment could not be completed or validated safely."""


@dataclass
class AssessmentRun:
    run_id: str
    model: str
    assessment: Assessment
    trace: list[dict]
    input_tokens: int
    output_tokens: int


def normalize_whitespace(text: str) -> str:
    """Ignore formatting differences while preserving words and punctuation."""
    return " ".join(text.split())


def validate_evidence(
    assessment: Assessment,
    scenario: str,
    retrieved_ids: set[str],
) -> None:
    """Check grounding constraints that do not require another model call."""
    question_ids = {
        question.policy_id for question in assessment.follow_up_questions
    }

    normalized_scenario = normalize_whitespace(scenario)

    expected_statuses = {
        "present": FindingStatus.SATISFIED,
        "explicitly_absent_or_inadequate": FindingStatus.GAP_IDENTIFIED,
        "unknown": FindingStatus.INSUFFICIENT_INFORMATION,
        "explicitly_not_applicable": FindingStatus.NOT_APPLICABLE,
    }

    for finding in assessment.findings:
        if finding.policy_id not in retrieved_ids:
            raise AssessmentError("A finding references an unretrieved policy.")

        expected_status = expected_statuses[finding.control_evidence]

        if finding.status != expected_status:
            raise AssessmentError(
                f"{finding.policy_id}: status conflicts with control evidence. "
                f"Evidence classified as {finding.control_evidence} "
                f"requires status {expected_status.value}."
            )

        for quote in finding.evidence_quotes:
            normalized_quote = normalize_whitespace(quote)

            if (
                not normalized_quote
                or normalized_quote not in normalized_scenario
            ):
                raise AssessmentError(
                    f"{finding.policy_id}: evidence does not match "
                    "the scenario after whitespace normalization."
                )

        if finding.status == FindingStatus.INSUFFICIENT_INFORMATION:
            if finding.policy_id not in question_ids:
                raise AssessmentError(
                    f"{finding.policy_id}: missing a follow-up question."
                )
        elif not finding.evidence_quotes:
            raise AssessmentError(
                f"{finding.policy_id}: this status requires scenario evidence."
            )

    if (
        assessment.risk_level == RiskLevel.HIGH
        and not assessment.additional_review_recommended
    ):
        raise AssessmentError("High-risk assessments require additional review.")


def assess_scenario(scenario: str) -> AssessmentRun:
    """Retrieve policy evidence and return a validated assessment."""
    scenario = scenario.strip()
    if not scenario or len(scenario) > MAX_SCENARIO_LENGTH:
        raise AssessmentError(
            f"Enter a scenario between 1 and {MAX_SCENARIO_LENGTH} characters."
        )

    load_dotenv(Path(__file__).resolve().parent / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        raise AssessmentError("OPENAI_API_KEY is not configured.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    run_id = str(uuid4())
    trace = []
    input_tokens = 0
    output_tokens = 0
    retrieved_ids: set[str] = set()
    messages = [{"role": "user", "content": scenario}]

    def record(event: str, **details) -> None:
        trace.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **details,
            }
        )

    def record_response(response, stage: str) -> None:
        nonlocal input_tokens, output_tokens

        if response.usage:
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

        record(
            "model_response",
            stage=stage,
            response_id=response.id,
            status=response.status,
        )

        if response.status != "completed":
            raise AssessmentError(
                "The model response was incomplete. No assessment was accepted."
            )

    record("assessment_started", run_id=run_id, model=model)

    with OpenAI(timeout=45.0, max_retries=0) as client:
        for _ in range(MAX_RETRIEVAL_ROUNDS):
            response = client.responses.create(
                model=model,
                instructions=ASSESSMENT_INSTRUCTIONS,
                input=messages,
                tools=[POLICY_TOOL],
                tool_choice="required",
                parallel_tool_calls=False,
                max_output_tokens=600,
                store=False,
            )
            record_response(response, "policy_retrieval")
            messages.extend(response.output)

            calls = [
                item for item in response.output
                if item.type == "function_call"
            ]
            if len(calls) != 1:
                raise AssessmentError("Expected exactly one policy tool call.")

            call = calls[0]
            if call.name != "get_policies":
                raise AssessmentError("The model requested an unsupported tool.")

            request = PolicyRequest.model_validate_json(call.arguments)
            policies = get_policies(request)
            returned_ids = [policy["id"] for policy in policies]
            retrieved_ids.update(returned_ids)

            record(
                "tool_executed",
                tool=call.name,
                requested_ids=request.policy_ids,
                returned_ids=returned_ids,
            )
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(policies),
                }
            )

            if retrieved_ids == EXPECTED_POLICY_IDS:
                break

            missing_ids = sorted(EXPECTED_POLICY_IDS - retrieved_ids)
            messages.append(
                {
                    "role": "developer",
                    "content": f"Retrieve remaining policies: {missing_ids}",
                }
            )
        else:
            raise AssessmentError(
                "Policy retrieval limit reached before all policies were retrieved."
            )

        final_instructions = (
            ASSESSMENT_INSTRUCTIONS
            + "\nRetrieval is complete. Produce the structured assessment now."
        )

        # Allow one correction attempt after application validation fails.
        for attempt in range(2):
            final_response = client.responses.parse(
                model=model,
                instructions=final_instructions,
                input=messages,
                text_format=Assessment,
                max_output_tokens=4_000,
                store=False,
            )
            record_response(final_response, "assessment")

            assessment = final_response.output_parsed
            if assessment is None:
                raise AssessmentError(
                    "The model did not return an assessment, "
                    "possibly due to a refusal."
                )

            try:
                validate_evidence(assessment, scenario, retrieved_ids)
            except AssessmentError as error:
                record(
                    "validation_failed",
                    attempt=attempt + 1,
                    reason=str(error),
                )

                if attempt == 1:
                    raise

                messages.extend(final_response.output)
                messages.append(
                    {
                        "role": "developer",
                        "content": (
                            f"Application validation failed: {error} "
                            "Return a corrected complete assessment. "
                            "Copy evidence directly from the original scenario. "
                            "Do not add punctuation or paraphrase excerpts. "
                            "Recheck every finding before returning the result. "
                            "For EACH finding whose status is "
                            "insufficient_information, include a follow-up "
                            "question with the SAME policy_id in "
                            "follow_up_questions. This includes AI-004 if its "
                            "logging and monitoring controls are unknown. "
                            "Preserve all eight findings and ensure each status "
                            "matches its control_evidence category."
                        ),
                    }
                )
                record("correction_requested", attempt=attempt + 1)
            else:
                break
    record(
        "validation_passed",
        checks=[
            "policy_coverage",
            "retrieved_policy_references",
            "control_evidence_status_consistency",
            "evidence_quotes_match_after_whitespace_normalization",
            "follow_up_questions",
            "high_risk_review",
        ],
    )

    return AssessmentRun(
        run_id=run_id,
        model=model,
        assessment=assessment,
        trace=trace,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )