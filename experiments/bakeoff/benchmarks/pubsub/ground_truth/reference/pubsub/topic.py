"""Topic — a named channel that handlers attach to."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    """A named channel.

    Topics are identified by name; publishing to ``Topic("orders")``
    delivers events to every handler registered against that name.
    Frozen + hashable so a Bus can use Topic instances as dict keys.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Topic name must be a non-empty string")
