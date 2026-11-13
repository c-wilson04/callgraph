from __future__ import annotations

import html
import json
from datetime import datetime
from importlib import resources
from typing import Any

PLACEHOLDER = "/*__CALLGRAPH_DATA__*/null"


def render_html(metrics: dict[str, Any], title: str | None = None) -> str:
    """Render a self-contained interactive dashboard (no network access needed)."""
    template = resources.files("callgraph.render").joinpath("dashboard.html").read_text(encoding="utf-8")
    data = dict(metrics)
    data["summary"] = {**metrics["summary"], "generated": datetime.now().strftime("%Y-%m-%d %H:%M")}
    payload = json.dumps(data, separators=(",", ":"))
    # Make the JSON safe to embed inside a <script> element.
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--")
    page_title = title or f"callgraph · {metrics['summary'].get('script') or 'trace'}"
    return template.replace("__TITLE__", html.escape(page_title)).replace(PLACEHOLDER, payload)
