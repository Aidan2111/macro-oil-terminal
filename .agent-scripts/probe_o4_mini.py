"""Directly hit o4-mini to see what errors out."""
import os, json
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)

messages = [
    {"role": "system", "content": "Return a JSON object with keys stance and confidence_0_to_10 only. No prose."},
    {"role": "user", "content": "What stance on Brent-WTI when dislocation=2.1?"},
]

for attempt_label, kwargs_extra in [
    ("baseline (no response_format)", {}),
    ("json_object", {"response_format": {"type": "json_object"}}),
    ("json_schema minimal", {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "tiny",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "stance": {"type": "string"},
                        "confidence_0_to_10": {"type": "number"},
                    },
                    "required": ["stance", "confidence_0_to_10"],
                },
                "strict": True,
            },
        }
    }),
]:
    try:
        print(f"\n--- {attempt_label} ---")
        resp = client.chat.completions.create(
            model="o4-mini",
            messages=messages,
            max_completion_tokens=800,
            **kwargs_extra,
        )
        print("OK len:", len(resp.choices[0].message.content or ""))
        print(resp.choices[0].message.content[:400])
    except Exception as e:
        print("FAIL:", repr(e)[:300])
