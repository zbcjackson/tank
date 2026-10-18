"""SDK-attempt denominators, with explicit missingness for historical rows."""

from typing import Any, Literal


def count_attempts(rows: list[dict[str, Any]], stage: Literal["intake", "fallback"]) -> int | None:
    purposes = ({"computer_use.intake"} if stage == "intake" else
                {"computer_use.fallback", "computer_use.visual_fallback"})
    legacy: set[tuple[int, int]] = set()
    starts: set[str] = set()
    finishes: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        events = row.get("events", [])
        modern = (row.get("result", {}).get("details", {}).get("model_call_metrics_version") == 2
                  or any(e.get("kind") == "model_call" and e.get("purpose") for e in events))
        if modern:
            for event in events:
                if event.get("kind") == "model_call" and event.get("purpose") in purposes:
                    call_id = event.get("call_id")
                    if not isinstance(call_id, str) or not call_id:
                        return None
                    if event.get("phase") == "started":
                        starts.add(call_id)
                    elif event.get("phase") == "finished":
                        status = event.get("status")
                        if status not in {"not_started", "returned", "unknown"}:
                            return None
                        finishes.setdefault(call_id, set()).add(status)
        elif stage == "fallback" and "events" in row:
            # Legacy selection events have no SDK identity. Count start only;
            # start/result pairs must never count as two calls.
            legacy.update((index, n) for n, e in enumerate(events)
                          if e.get("kind") == "computer_use_selection"
                          and e.get("stage") == "fallback" and e.get("phase") == "start")
        else:
            # A stored successful brief cannot establish how many intakes failed.
            return None
    # Admission starts before policy/capture checks. Only a correlated terminal
    # record establishes whether the SDK was invoked; incomplete traces stay unknown.
    if starts - finishes.keys() or any(
        len(statuses) != 1 or call_id not in starts and statuses != {"not_started"}
        for call_id, statuses in finishes.items()
    ):
        return None
    return len(legacy) + sum(statuses != {"not_started"} for statuses in finishes.values())
