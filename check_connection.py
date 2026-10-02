"""Check OpenAI connectivity without sending scenario data."""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    with OpenAI(timeout=30.0, max_retries=0) as client:
        response = client.responses.create(
            model=model,
            input="Reply with exactly: Connection successful",
            max_output_tokens=32,
            store=False,
        )

    if response.status != "completed":
        raise SystemExit(f"Request did not complete: {response.status}")

    print(response.output_text)


if __name__ == "__main__":
    main()