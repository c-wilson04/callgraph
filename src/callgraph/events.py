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
    timestamp_ns: int = 0
    thread_id: int = 0
    # CALL: a generator/coroutine resuming rather than a fresh call.
    resumed: bool = False
    # RETURN: the frame exited by raising an exception.
    raised: bool = False
