from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callgraph.model import FunctionIdentity


class EventType(Enum):
    CALL = "call"
    RETURN = "return"


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_type: EventType
    identity: FunctionIdentity
    caller: FunctionIdentity | None = None
