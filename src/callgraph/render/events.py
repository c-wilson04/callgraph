from __future__ import annotations

from callgraph.events import EventType, TraceEvent
from callgraph.model import CallTree


def render_events(tree: CallTree, events: list[TraceEvent]) -> str:
    del tree
    lines: list[str] = []
    for event in events:
        prefix = "CALL" if event.event_type is EventType.CALL else "RETURN"
        lines.append(f"{prefix} {event.identity.name}")
    return "\n".join(lines)
