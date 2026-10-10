"""Read-only AX adapter. Native handles stay outside model-facing snapshots."""

from uuid import uuid4

from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.tools.computer_ax import AXCandidate, ax_window_candidates
from tank_backend.tools.computer_native import run_native

from .contracts import Element, Operation, Snapshot

_ROLES = {"AXButton": "button", "AXMenuItem": "menuitem", "AXLink": "link",
          "AXCheckBox": "checkbox", "AXRadioButton": "radio", "AXTab": "tab",
          "AXTextField": "textbox", "AXTextArea": "textbox", "AXSearchField": "textbox"}


class AXObservationSource:
    """One task, one host-bound window/display; no capture or input side effects.

    The caller supplies a window/display binding. This adapter only enumerates its
    window, and must be called via the controller's registered read operation.
    A future executor must revalidate the frame and native target before input.
    """

    def __init__(self, window_id: int, display_geometry: tuple[int, ...], scope: str,
                 *, use_identifiers: bool = False) -> None:
        if window_id <= 0 or len(display_geometry) != 7 or not scope:
            raise ValueError("AX requires a bound window, display geometry and scope")
        self.window_id, self.display_geometry, self.scope = window_id, display_geometry, scope
        self.use_identifiers = use_identifiers
        self.closed = False
        self.task_id: str | None = None
        self.targets: list[tuple[str, AXCandidate]] = []
        self.previous: Snapshot | None = None
        self.document_bound = False
        self.document: str | None = None

    def scan(self) -> tuple[list[AXCandidate], bool]:
        if self.use_identifiers:
            return ax_window_candidates(self.window_id, self.display_geometry,
                                        include_descriptions=False)
        return ax_window_candidates(self.window_id, self.display_geometry)

    async def observe(self, scope: str, context: SubAgentContext) -> Snapshot:
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        if scope != self.scope:
            raise SubAgentStopped("scope_mismatch")
        if self.task_id is not None and self.task_id != context.runtime.task_id:
            raise SubAgentStopped("task_mismatch")
        self.task_id = context.runtime.task_id

        def read() -> tuple[list[AXCandidate], bool]:
            context.check("desktop")
            context.runtime.check_open()
            if self.closed:
                raise SubAgentStopped("channel_closed")
            return self.scan()

        candidates, truncated = await run_native(read)
        context.check("desktop")
        context.runtime.check_open()
        if self.closed:
            raise SubAgentStopped("channel_closed")
        documents = {item.window_document for item in candidates}
        if len(documents) > 1:
            raise SubAgentStopped("document_ambiguous")
        if documents:
            document = next(iter(documents))
            if self.document_bound and document != self.document:
                raise SubAgentStopped("document_changed")
            self.document, self.document_bound = document, True
        targets: list[tuple[str, AXCandidate]] = []
        elements = []
        for candidate in candidates:
            if candidate.window_id != self.window_id or candidate.pid is None:
                raise SubAgentStopped("scope_mismatch")
            ref = next((ref for ref, old in (*self.targets, *targets)
                        if old.pid == candidate.pid and old.window_id == candidate.window_id
                        and old.element.native == candidate.element.native), uuid4().hex)
            # Duplicate native objects are one element, even if the AX tree links twice.
            if any(existing == ref for existing, _ in targets):
                continue
            targets.append((ref, candidate))
            actions: list[Operation] = []
            if "AXPress" in candidate.actions:
                actions.append("click")
            if _ROLES.get(candidate.role) == "textbox" and candidate.value_settable:
                actions.append("fill")
            role = _ROLES.get(candidate.role, candidate.role)
            label = (candidate.identifier or candidate.title if self.use_identifiers else
                     candidate.title or candidate.description or candidate.identifier)
            label = label or (candidate.role if role == "textbox" else candidate.value)
            # Shared AX titles are common for stacked text views; keep fills distinguishable.
            if (role == "textbox" and not self.use_identifiers and candidate.identifier
                    and label != candidate.identifier):
                label = f"{label} · {candidate.identifier}"
            elements.append(Element(
                ref, _ROLES.get(candidate.role, candidate.role),
                label,
                tuple(actions), candidate.enabled is True,
                "control" if actions else "text_region", "ax", candidate.value,
                candidate.focused, candidate.ancestors, candidate.frame,
            ))
        generation = 0 if self.previous is None else self.previous.generation
        if self.previous is not None and (
            tuple(elements) != self.previous.elements or (not truncated) != self.previous.complete
        ):
            generation += 1
        snapshot = Snapshot(uuid4().hex, scope, generation, tuple(elements), complete=not truncated,
                            window=str(self.window_id))
        self.targets, self.previous = targets, snapshot
        return snapshot

    async def aclose(self) -> None:
        self.closed = True
        self.targets.clear()
        self.previous = None
