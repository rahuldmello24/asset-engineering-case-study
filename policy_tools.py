"""Read-only access to Acme's AI governance requirements."""

import json
from pathlib import Path

from pydantic import Field, TypeAdapter

from schemas import EXPECTED_POLICY_IDS, PolicyId, StrictModel


POLICY_FILE = Path(__file__).resolve().parent / "data" / "policies.json"


class Policy(StrictModel):
    id: PolicyId
    requirement: str = Field(min_length=1)


class PolicyRequest(StrictModel):
    policy_ids: list[PolicyId] = Field(
        max_length=8,
        description=(
            "Policy IDs to retrieve. "
            "An empty list retrieves all eight Acme requirements."
        ),
    )


def load_policies() -> list[Policy]:
    """Load and validate the trusted policy reference file."""
    with POLICY_FILE.open(encoding="utf-8") as policy_file:
        raw_policies = json.load(policy_file)

    policies = TypeAdapter(list[Policy]).validate_python(raw_policies)
    actual_ids = {policy.id for policy in policies}

    if (
        len(policies) != len(EXPECTED_POLICY_IDS)
        or actual_ids != EXPECTED_POLICY_IDS
    ):
        raise ValueError(
            "The policy file must contain each Acme policy exactly once."
        )

    return policies


def get_policies(request: PolicyRequest) -> list[dict[str, str]]:
    """Return requested policies in their reference-file order."""
    policies = load_policies()
    selected_ids = set(request.policy_ids)

    return [
        policy.model_dump()
        for policy in policies
        if not selected_ids or policy.id in selected_ids
    ]