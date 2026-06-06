"""Singleton sentinels used in KB query results.

The schema sentinel ``{"kind": "not_applicable"}`` decodes to ``NotApplicable``
on the Python side. Use ``value is NotApplicable`` for identity checks; the
class is frozen and the singleton is module-level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class _NotApplicableSentinel:
    def __repr__(self) -> str:
        return "NotApplicable"


NotApplicable: Final = _NotApplicableSentinel()
