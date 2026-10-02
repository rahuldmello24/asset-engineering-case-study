"""Manual integration check using a fictional scenario."""

import json

from agent import assess_scenario


SCENARIO = """
A customer support team wants to use an LLM to summarize customer
conversations and suggest responses to support agents. The system will
process customer names, account information, support tickets, and
conversation history. A human support agent will review the generated
response before sending it to the customer. The application will use a
third-party hosted LLM API.
"""


if __name__ == "__main__":
    result = assess_scenario(SCENARIO)

    print(result.assessment.model_dump_json(indent=2))
    print("\nExecution trace:")
    print(json.dumps(result.trace, indent=2))
    print(
        f"\nTokens: {result.input_tokens} input, "
        f"{result.output_tokens} output"
    )