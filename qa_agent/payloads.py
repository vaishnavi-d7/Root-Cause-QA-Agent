"""Test payloads and payload generators for form fuzzing."""
from typing import Any, Dict, List

TEXT_PAYLOADS: List[str] = [
    "",
    " ",
    "'",
    '"',
    "' OR '1'='1",
    "%",
    "_",
    "a" * 3000,
    "../../etc/passwd",
    "<script>alert(1)</script>",
    "unicode text with emoji 🚀",
    "{{7*7}}",
    "-1",
    "0",
    "null",
]

NUMBER_PAYLOADS: List[str] = [
    "",
    "0",
    "-1",
    "1.5",
    "999999999999999999999",
    "1e3",
]


def static_payloads(field: Dict[str, Any]) -> List[str]:
    """Pick static test payloads according to input field type."""
    field_type = str(field.get("type", "text")).lower()
    tag = str(field.get("tag", "input")).lower()
    if tag == "input" and field_type == "number":
        return NUMBER_PAYLOADS
    return TEXT_PAYLOADS


def llm_payloads(form: Dict[str, Any], limit: int = 8) -> Dict[str, List[str]]:
    """Query LLM for adversarial form payloads, gracefully falling back on failure."""
    try:
        from llm_client import LLMClient
        import json

        client = LLMClient()
        fields = [f["name"] for f in form.get("fields", []) if f.get("name")]
        prompt = (
            f"Generate {limit} adversarial test inputs per form field for a web form. "
            f"Return JSON format {{field_name: [list of strings]}} ONLY. Fields: {fields}"
        )
        response_text = client.ask(prompt)
        data = json.loads(response_text)
        if isinstance(data, dict):
            return {
                str(k): [str(x) for x in v[:limit]]
                for k, v in data.items()
                if isinstance(v, list)
            }
        return {}
    except Exception as e:
        print(f"[llm_payloads] Using static payloads fallback: {e}")
        return {}
