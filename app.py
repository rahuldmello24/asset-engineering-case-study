"""Streamlit interface for the Acme AI governance assessor."""

import json

import streamlit as st
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError

from agent import AssessmentError, MAX_SCENARIO_LENGTH, assess_scenario
from policy_tools import load_policies
from schemas import FindingStatus


STATUS_LABELS = {
    FindingStatus.SATISFIED: "Satisfied",
    FindingStatus.GAP_IDENTIFIED: "Gap identified",
    FindingStatus.INSUFFICIENT_INFORMATION: "Insufficient information",
    FindingStatus.NOT_APPLICABLE: "Not applicable",
}


def render_result(saved: dict) -> None:
    run = saved["run"]
    assessment = run.assessment
    policies = saved["policies"]

    st.divider()
    st.subheader("Assessment results")
    st.caption(f"Run ID: {run.run_id} | Model: {run.model}")

    risk_column, gaps_column, unknowns_column = st.columns(3)
    risk_column.metric("Risk level", assessment.risk_level.value.title())
    gaps_column.metric(
        "Identified gaps",
        sum(
            finding.status == FindingStatus.GAP_IDENTIFIED
            for finding in assessment.findings
        ),
    )
    unknowns_column.metric(
        "Require clarification",
        sum(
            finding.status == FindingStatus.INSUFFICIENT_INFORMATION
            for finding in assessment.findings
        ),
    )

    st.text(assessment.summary)
    st.text(f"Risk rationale: {assessment.risk_rationale}")

    if assessment.additional_review_recommended:
        st.warning("Additional human review recommended.")
    else:
        st.info("No additional review recommended by this initial assessment.")

    st.caption(
        "Risk levels use a demonstration rubric, not an official Acme "
        "classification. Additional review can be precautionary."
    )

    with st.expander("Scenario used for this assessment"):
        st.text(saved["scenario"])

    findings_tab, questions_tab, trace_tab = st.tabs(
        ["Policy findings", "Follow-up questions", "Execution trace"]
    )

    with findings_tab:
        for finding in assessment.findings:
            label = STATUS_LABELS[finding.status]
            with st.expander(
                f"{finding.policy_id} — {label}",
                expanded=finding.status == FindingStatus.GAP_IDENTIFIED,
            ):
                st.markdown("**Acme requirement**")
                st.text(policies[finding.policy_id])

                st.markdown("**Scenario evidence**")
                if finding.evidence_quotes:
                    for quote in finding.evidence_quotes:
                        st.text(f'“{quote}”')
                else:
                    st.caption("No supporting scenario excerpt provided.")

                st.markdown("**Rationale**")
                st.text(finding.rationale)

                st.markdown("**Recommended action**")
                st.text(finding.recommended_action)

    with questions_tab:
        if not assessment.follow_up_questions:
            st.info("No follow-up questions were generated.")

        for question in assessment.follow_up_questions:
            st.text(f"{question.policy_id}: {question.question}")

    with trace_tab:
        st.caption(
            "Observable execution events. Validation checks structure and "
            "evidence matching; it does not verify every conclusion."
        )
        st.json(run.trace)
        st.text(
            f"Token usage: {run.input_tokens:,} input / "
            f"{run.output_tokens:,} output"
        )

    export = {
        "run_id": run.run_id,
        "model": run.model,
        "scenario": saved["scenario"],
        "policy_reference": policies,
        "assessment": assessment.model_dump(mode="json"),
        "trace": run.trace,
        "usage": {
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
        },
        "limitations": [
            "Advisory assessment, not compliance certification.",
            "Risk classification uses a demonstration rubric.",
            "Evidence matching does not establish conclusion correctness.",
        ],
    }

    st.download_button(
        "Download assessment JSON",
        data=json.dumps(export, indent=2),
        file_name=f"acme-assessment-{run.run_id}.json",
        mime="application/json",
    )
    st.caption("The download includes the submitted scenario and evidence.")


def main() -> None:
    st.set_page_config(
        page_title="Acme AI Governance Assessor",
        layout="wide",
    )

    st.title("Acme AI Governance Assessor")
    st.write(
        "Assess an AI use case against Acme's eight security "
        "and governance requirements."
    )
    st.info(
        "Use fictional or sanitized scenarios. Submitted text is sent to "
        "OpenAI for analysis. Do not enter credentials or real confidential data."
    )

    with st.form("assessment_form"):
        scenario = st.text_area(
            "Describe the AI use case",
            height=220,
            max_chars=MAX_SCENARIO_LENGTH,
            placeholder=(
                "Describe the purpose, data processed, business owner, "
                "human oversight, hosting, and known security controls."
            ),
        )
        submitted = st.form_submit_button("Assess scenario")

    if submitted:
        # Clear prior results so a failed request cannot show an old assessment.
        st.session_state.pop("assessment_result", None)

        if not scenario.strip():
            st.error("Enter a scenario before requesting an assessment.")
        else:
            try:
                policies = {
                    policy.id: policy.requirement for policy in load_policies()
                }
                with st.spinner("Retrieving policies and assessing the scenario…"):
                    run = assess_scenario(scenario)

                st.session_state["assessment_result"] = {
                    "run": run,
                    "scenario": scenario.strip(),
                    "policies": policies,
                }
            except AuthenticationError:
                st.error("Authentication failed. Check your local API configuration.")
            except RateLimitError:
                st.error("API quota or rate limit reached. Check your API account.")
            except (APITimeoutError, APIConnectionError):
                st.error("The API could not be reached in time. Please try again.")
            except APIStatusError:
                st.error("The API rejected the request. Check model access and configuration.")
            except AssessmentError as error:
                st.error(str(error))
            except (ValidationError, ValueError):
                st.error(
                    "Policy data or model output failed validation. "
                    "No assessment was accepted."
                )
            except OSError:
                st.error("The policy reference file could not be read.")

    saved = st.session_state.get("assessment_result")
    if saved is not None:
        render_result(saved)

    st.divider()
    st.caption(
        "Advisory prototype. Findings are based on the submitted description "
        "and require human review. 'Satisfied' does not mean independently verified."
    )


if __name__ == "__main__":
    main()