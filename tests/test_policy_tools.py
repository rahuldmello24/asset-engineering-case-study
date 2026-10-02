"""Tests for policy retrieval and argument validation."""

import pytest
from pydantic import ValidationError

from policy_tools import PolicyRequest, get_policies
from schemas import EXPECTED_POLICY_IDS


def test_empty_selection_returns_all_policies():
    policies = get_policies(PolicyRequest(policy_ids=[]))

    assert len(policies) == 8
    assert {policy["id"] for policy in policies} == EXPECTED_POLICY_IDS
    assert all(policy["requirement"].strip() for policy in policies)


def test_selected_policies_are_returned():
    policies = get_policies(
        PolicyRequest(policy_ids=["AI-002", "AI-006"])
    )

    assert {policy["id"] for policy in policies} == {
        "AI-002",
        "AI-006",
    }


def test_unknown_policy_is_rejected():
    with pytest.raises(ValidationError):
        PolicyRequest.model_validate({"policy_ids": ["AI-999"]})


def test_arbitrary_file_argument_is_rejected():
    with pytest.raises(ValidationError):
        PolicyRequest.model_validate(
            {
                "policy_ids": [],
                "file_path": ".env",
            }
        )