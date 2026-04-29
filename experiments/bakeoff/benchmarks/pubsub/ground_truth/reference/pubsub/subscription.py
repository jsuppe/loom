"""Subscription — token returned by Bus.subscribe.

Held by a caller to identify their handler registration; used to
unsubscribe later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Subscription:
    """Token identifying a registered handler.

    Created by :class:`Bus` when a handler is registered. The Bus
    owns the canonical mapping from topic to handlers; this token
    just lets the caller cancel its specific registration.
    """

    id: str
    topic_name: str
    handler: Callable[[object], None]
    _closed: bool = field(default=False, repr=False)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True
