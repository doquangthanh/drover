"""Turn noisy per-frame detections into stable pane states with debounce.

Public states: working | blocked | idle | done | exited | stopped
- `done` = a working -> idle transition, kept until the user looks at the pane.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

DEBOUNCE_SECONDS = 0.5
ACTIVITY_WINDOW = 1.5  # generic fallback: output within this window = working


@dataclass
class StatusTracker:
    state: str = "idle"
    since: float = field(default_factory=time.time)
    _candidate: str | None = None
    _candidate_at: float = 0.0
    reported: str | None = None  # from OSC 7501, authoritative while fresh
    reported_at: float = 0.0
    hold_until: float = 0.0  # after new input, don't fall back to idle/done before the agent reacts
    detected_working_at: float = 0.0  # last frame that *looked* busy (not the state forced by new input)

    def observe(self, detected: str | None, last_output_at: float, focused: bool, now: float | None = None,
                allow_done: bool = True) -> str | None:
        """Feed one detection. Returns the new public state if it changed, else None."""
        now = now or time.time()
        if self.state in ("exited", "stopped"):
            return None
        if self.reported and now - self.reported_at < 30:
            detected = "idle" if self.reported == "done" else self.reported
        if detected is None:
            detected = "working" if now - last_output_at < ACTIVITY_WINDOW else "idle"
        if detected in ("working", "blocked"):
            self.detected_working_at = now
        if detected == "idle" and now < self.hold_until:
            return None
        if detected != self._candidate:
            self._candidate, self._candidate_at = detected, now
            return None
        if now - self._candidate_at < DEBOUNCE_SECONDS:
            return None
        target = detected
        if detected == "idle" and self.state == "working" and not focused and allow_done:
            target = "done"
        if detected == "idle" and self.state == "done":
            return None  # stay done until acknowledged
        if target == self.state:
            return None
        self.state, self.since = target, now
        return target

    def acknowledge(self) -> str | None:
        """User looked at the pane: done -> idle."""
        if self.state == "done":
            self.state, self.since = "idle", time.time()
            return "idle"
        return None

    def report(self, state: str) -> None:
        self.reported, self.reported_at = state, time.time()

    def mark_exited(self) -> str:
        self.state, self.since = "exited", time.time()
        return self.state
