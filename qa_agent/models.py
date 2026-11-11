"""Data models and route/step utilities for the QA agent."""
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def normalise_route(url: str) -> str:
    """Return URL path with all numeric segments replaced by <n>."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    segments = path.split("/")
    norm_segments = [
        "<n>" if seg.isdigit() or (seg.startswith("-") and seg[1:].isdigit()) else seg
        for seg in segments
    ]
    norm_path = "/".join(norm_segments)
    return norm_path if norm_path else "/"


def format_step_value(value: Any) -> str:
    """Format step value showing (empty) or truncating values over 40 characters."""
    val_str = str(value)
    if val_str == "":
        return "(empty)"
    if len(val_str) > 40:
        return f"`{val_str[:37]}...` ({len(val_str)} chars)"
    return f"`{val_str}`"


def extract_field_name(selector: str) -> str:
    """Extract input field name from Playwright selector string."""
    match = re.search(r'\[name=["\']?([^"\'\]]+)["\']?\]', selector)
    if match:
        return match.group(1)
    return selector


def describe_steps(steps: List[Dict[str, Any]]) -> List[str]:
    """Convert replayable action steps into human-readable sentences."""
    sentences: List[str] = []
    for step in steps:
        action = step.get("action", "")
        if action == "goto":
            url = step.get("url", "")
            parsed = urllib.parse.urlparse(url)
            display_url = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            display_url = display_url if display_url else url
            sentences.append(f"Open `{display_url}`")
        elif action == "fill":
            sel = step.get("selector", "")
            val = format_step_value(step.get("value", ""))
            field = extract_field_name(sel)
            sentences.append(f"Type {val} into the **{field}** field")
        elif action == "select":
            sel = step.get("selector", "")
            val = format_step_value(step.get("value", ""))
            field = extract_field_name(sel)
            sentences.append(f"Choose {val} in the **{field}** dropdown")
        elif action == "submit":
            sentences.append("Click the form's submit button")
    return sentences


@dataclass
class Finding:
    """Represents a unique defect discovered by the QA agent."""

    id: str
    kind: str
    method: str
    url: str
    route: str
    status: Optional[int]
    summary: str
    steps: List[Dict[str, Any]]
    console: List[str]
    screenshot: Optional[str] = None
    video: Optional[str] = None
    reproduced: Optional[bool] = None
    occurrences: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "kind": self.kind,
            "method": self.method,
            "url": self.url,
            "route": self.route,
            "status": self.status,
            "summary": self.summary,
            "steps": self.steps,
            "console": self.console,
            "screenshot": self.screenshot,
            "video": self.video,
            "reproduced": self.reproduced,
            "occurrences": self.occurrences,
        }
