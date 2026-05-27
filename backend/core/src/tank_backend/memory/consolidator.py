"""Dream Consolidation pipeline — idle/scheduled memory curator.

Three-phase pipeline run at most once per ``interval_hours`` per user:

* **Phase 1 (Light scan)** — pull every preference and mem0 fact for the
  user, score each candidate by a six-factor weighted sum, keep the
  top-K for the LLM.
* **Phase 2 (REM)** — single LLM call that classifies each top-K
  candidate as ``promote`` (move from inferred → pinned), ``consolidate``
  (which is canonical, which are duplicates), ``archive`` (stale or
  contradicted), or ``keep`` (leave as-is).
* **Phase 3 (Deep apply)** — apply the verdicts to
  :class:`PreferenceStore` and append a dated entry to
  ``~/.tank/DREAMS.md`` for human inspection.

Run isolation: the consolidator uses its own ``consolidation`` LLM
profile (falling back to ``default``) so background dreaming never
pollutes the main session's prompt cache.

Failure is non-fatal at every step — a broken LLM call returns an empty
report; the user's memory stays untouched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..config.models import ConsolidationWeights

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam

    from ..llm.llm import LLM
    from ..preferences.store import PreferenceStore
    from .service import MemoryService

logger = logging.getLogger(__name__)


VerdictAction = Literal["promote", "consolidate", "archive", "keep"]
CandidateSource = Literal["preference", "memory"]


@dataclass(frozen=True)
class ConsolidationCandidate:
    """One fact under consideration for promotion / consolidation / archival."""

    text: str
    source: CandidateSource
    age_days: float
    score: float = 0.0


@dataclass(frozen=True)
class ConsolidationVerdict:
    """LLM's call on one candidate.

    ``winner`` and ``losers`` are only meaningful for ``consolidate``.
    """

    text: str
    action: VerdictAction
    winner: str | None = None
    losers: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class ConsolidationReport:
    """Outcome of one consolidator.run() invocation."""

    started_at: datetime
    finished_at: datetime
    user: str
    candidates_scanned: int
    promoted: list[str] = field(default_factory=list)
    consolidated: list[tuple[str, list[str]]] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class Consolidator:
    """Idle/scheduled curator for preferences and mem0 facts.

    Stateless apart from the diary path. Safe to share across users —
    one instance per backend is plenty.
    """

    def __init__(
        self,
        *,
        llm: LLM,
        memory: MemoryService | None,
        preferences: PreferenceStore,
        diary_filename: str,
        weights: ConsolidationWeights,
        top_k: int = 20,
        min_idle_minutes: int = 30,
        interval_hours: int = 24,
        llm_timeout_seconds: float = 60.0,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._preferences = preferences
        self._diary_filename = diary_filename
        self._weights = weights
        self._top_k = top_k
        self._min_idle_seconds = min_idle_minutes * 60
        self._interval_seconds = interval_hours * 3600
        self._llm_timeout = llm_timeout_seconds
        self._clock = clock
        # In-memory last-run cache. Persisted via the diary file when we
        # need cross-restart timestamps; this is just the hot path.
        self._last_run: dict[str, datetime] = {}

    async def run(
        self,
        user: str,
        *,
        force: bool = False,
        last_user_activity: datetime | None = None,
    ) -> ConsolidationReport:
        """Run one consolidation pass for ``user``.

        Respects ``min_idle_minutes`` and ``interval_hours`` unless
        ``force=True``. The caller is responsible for sourcing
        ``last_user_activity`` if it wants the idle gate enforced.
        """
        started = self._clock()

        if not force:
            if not self._idle_ok(started, last_user_activity):
                logger.debug("Consolidator: user %s not idle yet", user)
                return ConsolidationReport(
                    started_at=started, finished_at=started,
                    user=user, candidates_scanned=0,
                    error="not_idle",
                )
            if not self._interval_ok(user, started):
                logger.debug("Consolidator: user %s ran recently", user)
                return ConsolidationReport(
                    started_at=started, finished_at=started,
                    user=user, candidates_scanned=0,
                    error="interval",
                )

        try:
            candidates = await self._phase1_light_scan(user)
        except Exception as exc:
            logger.warning(
                "Consolidator: light scan failed for %s",
                user, exc_info=True,
            )
            return ConsolidationReport(
                started_at=started, finished_at=self._clock(),
                user=user, candidates_scanned=0, error=str(exc),
            )

        if not candidates:
            finished = self._clock()
            self._last_run[user] = finished
            return ConsolidationReport(
                started_at=started, finished_at=finished,
                user=user, candidates_scanned=0,
            )

        verdicts: list[ConsolidationVerdict] = []
        try:
            verdicts = await self._phase2_rem(user, candidates)
        except Exception as exc:
            logger.warning(
                "Consolidator: REM phase failed for %s",
                user, exc_info=True,
            )
            finished = self._clock()
            return ConsolidationReport(
                started_at=started, finished_at=finished,
                user=user, candidates_scanned=len(candidates),
                error=str(exc),
            )

        promoted, consolidated, archived = self._phase3_deep_apply(
            user, verdicts,
        )

        finished = self._clock()
        self._last_run[user] = finished
        report = ConsolidationReport(
            started_at=started, finished_at=finished,
            user=user, candidates_scanned=len(candidates),
            promoted=promoted, consolidated=consolidated, archived=archived,
        )
        self._write_diary_entry(report)
        return report

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    def _idle_ok(
        self, now: datetime, last_activity: datetime | None,
    ) -> bool:
        if last_activity is None:
            return True
        delta = (now - last_activity).total_seconds()
        return delta >= self._min_idle_seconds

    def _interval_ok(self, user: str, now: datetime) -> bool:
        previous = self._last_run.get(user)
        if previous is None:
            # Best-effort: peek at the diary for the most recent entry
            # for this user. The diary is the source of truth across
            # restarts.
            previous = self._read_last_diary_run(user)
        if previous is None:
            return True
        delta = (now - previous).total_seconds()
        return delta >= self._interval_seconds

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    async def _phase1_light_scan(
        self, user: str,
    ) -> list[ConsolidationCandidate]:
        """Build the candidate pool and score it.

        Pulls everything we know (preferences + mem0 facts), scores each
        entry by the six-factor sum, and returns the top-K by score.
        """
        prefs_text = self._preferences.list_for_user(user)
        memory_text: list[str] = []
        if self._memory is not None:
            try:
                memory_text = await self._memory.get_all(user)
            except Exception:
                logger.debug(
                    "Consolidator: mem0 get_all failed for %s",
                    user, exc_info=True,
                )

        now = self._clock()
        raw: list[ConsolidationCandidate] = []
        for text in prefs_text:
            age = _age_days_from_preference_line(text, now=now)
            raw.append(ConsolidationCandidate(
                text=text, source="preference", age_days=age,
            ))
        for text in memory_text:
            raw.append(ConsolidationCandidate(
                text=text, source="memory", age_days=0.0,
            ))

        if not raw:
            return []

        scored = self._score_candidates(raw)
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[: self._top_k]

    async def _phase2_rem(
        self,
        user: str,
        candidates: list[ConsolidationCandidate],
    ) -> list[ConsolidationVerdict]:
        """Ask the LLM to classify each candidate."""
        prompt = _build_rem_prompt(user, candidates)
        messages: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": prompt}
        ]
        response = await asyncio.wait_for(
            self._llm.complete(messages, temperature=0.2, max_tokens=2000),
            timeout=self._llm_timeout,
        )
        return _parse_rem_response(response)

    def _phase3_deep_apply(
        self,
        user: str,
        verdicts: list[ConsolidationVerdict],
    ) -> tuple[list[str], list[tuple[str, list[str]]], list[str]]:
        """Apply the verdicts to the preference store. Returns the same
        tuples the :class:`ConsolidationReport` reports.
        """
        promoted: list[str] = []
        consolidated: list[tuple[str, list[str]]] = []
        archived: list[str] = []

        for verdict in verdicts:
            try:
                if verdict.action == "promote":
                    if self._preferences.add_if_new(
                        user, verdict.text, source="pinned",
                    ):
                        promoted.append(verdict.text)
                    else:
                        # add_if_new returns False on duplicate — try a
                        # remove+re-add to flip the existing entry's
                        # source to pinned. Existing API doesn't expose
                        # a direct "promote" but remove+add covers it.
                        self._preferences.remove(user, verdict.text)
                        if self._preferences.add_if_new(
                            user, verdict.text, source="pinned",
                        ):
                            promoted.append(verdict.text)
                elif verdict.action == "consolidate":
                    if not verdict.winner:
                        continue
                    self._preferences.reinforce(user, verdict.winner)
                    losers_removed: list[str] = []
                    for loser in verdict.losers:
                        if loser == verdict.winner:
                            continue
                        if self._preferences.remove(user, loser):
                            losers_removed.append(loser)
                    if losers_removed:
                        consolidated.append((verdict.winner, losers_removed))
                elif verdict.action == "archive" and \
                        self._preferences.remove(user, verdict.text):
                    archived.append(verdict.text)
                # keep: no-op
            except Exception:
                logger.debug(
                    "Consolidator: applying verdict failed for %r",
                    verdict.text, exc_info=True,
                )

        return promoted, consolidated, archived

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_candidates(
        self, candidates: list[ConsolidationCandidate],
    ) -> list[ConsolidationCandidate]:
        """Apply the six-factor weighted sum.

        - **frequency**: 1.0 if the candidate appears as both a
          preference and a memory entry (cross-store duplication signals
          repeated reinforcement). Else 0.5 for preferences, 0.3 for
          memory-only.
        - **relevance**: mean Jaccard overlap vs. all other candidates
          (proxy for centrality without embedding lookups).
        - **diversity**: 1 - max Jaccard vs. any other candidate.
        - **recency**: exponential decay with 90-day half-life.
        - **consolidation**: 1.0 when any other candidate has Jaccard
          >= 0.5 (signals "has a near-duplicate, please merge").
        - **conceptual**: length-normalised — favours longer, more
          abstract statements (>30 chars saturates).
        """
        token_sets = [_token_set(c.text) for c in candidates]
        n = len(candidates)
        out: list[ConsolidationCandidate] = []

        text_index: dict[str, list[CandidateSource]] = {}
        for c in candidates:
            text_index.setdefault(c.text, []).append(c.source)

        for i, candidate in enumerate(candidates):
            sims: list[float] = []
            max_sim = 0.0
            for j in range(n):
                if i == j:
                    continue
                sim = _jaccard(token_sets[i], token_sets[j])
                sims.append(sim)
                if sim > max_sim:
                    max_sim = sim

            mean_sim = sum(sims) / len(sims) if sims else 0.0

            sources = text_index.get(candidate.text, [])
            if len(set(sources)) > 1:
                frequency = 1.0
            elif candidate.source == "preference":
                frequency = 0.5
            else:
                frequency = 0.3

            recency = _recency_score(candidate.age_days)
            diversity = 1.0 - max_sim
            consolidation = 1.0 if max_sim >= 0.5 else 0.0
            conceptual = min(len(candidate.text) / 30.0, 1.0)

            w = self._weights
            score = (
                w.frequency * frequency
                + w.relevance * mean_sim
                + w.diversity * diversity
                + w.recency * recency
                + w.consolidation * consolidation
                + w.conceptual * conceptual
            )
            out.append(ConsolidationCandidate(
                text=candidate.text,
                source=candidate.source,
                age_days=candidate.age_days,
                score=score,
            ))
        return out

    # ------------------------------------------------------------------
    # Diary
    # ------------------------------------------------------------------

    def _diary_path(self, user: str) -> Path:
        """Resolve the diary path for ``user`` via the preference store.

        Co-located with ``preferences.md`` under
        ``{base_dir}/users/{slug}/{diary_filename}``.
        """
        return self._preferences.user_file_path(user, self._diary_filename)

    def _write_diary_entry(self, report: ConsolidationReport) -> None:
        try:
            path = self._diary_path(report.user)
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = _format_diary_entry(report)
            with path.open("a", encoding="utf-8") as fp:
                fp.write(entry)
        except Exception:
            logger.warning(
                "Consolidator: failed to write diary for user=%s",
                report.user, exc_info=True,
            )

    def _read_last_diary_run(self, user: str) -> datetime | None:
        try:
            path = self._diary_path(user)
            if not path.exists():
                return None
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Parse the most recent ``## <iso-timestamp>`` heading.
        last: datetime | None = None
        for line in text.splitlines():
            match = re.match(r"^##\s+(\S+)\s*$", line)
            if not match:
                continue
            try:
                ts = datetime.fromisoformat(match.group(1))
            except ValueError:
                continue
            if last is None or ts > last:
                last = ts
        return last


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_consolidator(app_config: Any) -> Consolidator | None:
    """Wire a :class:`Consolidator` from app config.

    Returns ``None`` when:
    - ``preferences`` is disabled (no store to write into)
    - no usable LLM profile is available

    The mem0 layer is optional — its absence just means scoring uses
    only preference candidates.
    """
    from ..config.models import MemoryConfig
    from ..config.parser import ConfigError
    from ..llm.profile import create_llm_from_profile
    from ..preferences import PreferenceStore
    from .service import MemoryService

    cons_cfg = app_config.consolidation
    prefs_cfg = app_config.preferences
    if not prefs_cfg.enabled:
        return None

    base_dir = Path(prefs_cfg.base_dir or "~/.tank").expanduser()
    store = PreferenceStore(base_dir, prefs_cfg.max_entries)

    profile_name = cons_cfg.llm_profile
    try:
        profile = app_config.get_llm_profile(profile_name)
    except (KeyError, ValueError, ConfigError):
        try:
            profile = app_config.get_llm_profile("default")
        except (KeyError, ValueError, ConfigError):
            return None
    llm = create_llm_from_profile(profile)

    memory_service: MemoryService | None = None
    mem_cfg = app_config.memory
    if mem_cfg.enabled:
        try:
            default_profile = app_config.get_llm_profile("default")
        except (KeyError, ValueError, ConfigError):
            default_profile = None
        if default_profile is not None:
            resolved = MemoryConfig(
                enabled=True,
                db_path=mem_cfg.db_path,
                llm_api_key=mem_cfg.llm_api_key or default_profile.api_key,
                llm_base_url=mem_cfg.llm_base_url or default_profile.base_url,
                llm_model=mem_cfg.llm_model or "",
                embedding_api_key=mem_cfg.embedding_api_key or "",
                embedding_base_url=mem_cfg.embedding_base_url or "",
                embedding_model=mem_cfg.embedding_model or "",
                search_limit=mem_cfg.search_limit,
            )
            try:
                memory_service = MemoryService(resolved)
            except Exception:
                logger.warning(
                    "build_consolidator: MemoryService init failed",
                    exc_info=True,
                )

    return Consolidator(
        llm=llm,
        memory=memory_service,
        preferences=store,
        diary_filename=cons_cfg.diary_filename,
        weights=cons_cfg.weights,
        top_k=cons_cfg.top_k_candidates,
        min_idle_minutes=cons_cfg.min_idle_minutes,
        interval_hours=cons_cfg.interval_hours,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_rem_prompt(
    user: str, candidates: list[ConsolidationCandidate],
) -> str:
    bullets = "\n".join(
        f"- ({c.source}) {c.text}" for c in candidates
    )
    return f"""\
You are a careful memory curator for an assistant.

For each candidate fact about user "{user}", choose exactly one action:

- "promote"      — durable user truth that should never decay
                   (e.g. "Allergic to peanuts", "Lives in Berlin").
- "consolidate"  — one canonical form of a fact + its near-duplicates.
                   Pick a winner and list losers verbatim.
- "archive"      — stale, contradicted, or no longer useful.
- "keep"         — leave as-is.

When in doubt, "keep". Do NOT invent new facts.

Candidates:
{bullets}

Return strictly this JSON shape (no markdown fences, no commentary):

{{
  "verdicts": [
    {{"text": "...", "action": "promote",     "reason": "..."}},
    {{"text": "...", "action": "consolidate", "winner": "...", "losers": ["..."], "reason": "..."}},
    {{"text": "...", "action": "archive",     "reason": "..."}},
    {{"text": "...", "action": "keep",        "reason": "..."}}
  ]
}}

JSON:"""


def _parse_rem_response(text: str) -> list[ConsolidationVerdict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Consolidator: failed to parse REM JSON: %s", text)
        return []

    if not isinstance(parsed, dict):
        return []

    raw_verdicts = parsed.get("verdicts")
    if not isinstance(raw_verdicts, list):
        return []

    out: list[ConsolidationVerdict] = []
    for item in raw_verdicts:
        if not isinstance(item, dict):
            continue
        text_field = item.get("text")
        action = item.get("action")
        if not isinstance(text_field, str) or not text_field.strip():
            continue
        if action not in ("promote", "consolidate", "archive", "keep"):
            continue
        winner = item.get("winner") if isinstance(item.get("winner"), str) else None
        losers = item.get("losers")
        loser_tuple: tuple[str, ...] = ()
        if isinstance(losers, list):
            loser_tuple = tuple(
                str(loser).strip() for loser in losers
                if isinstance(loser, str) and loser.strip()
            )
        reason = item.get("reason")
        out.append(ConsolidationVerdict(
            text=text_field.strip(),
            action=action,
            winner=winner.strip() if winner else None,
            losers=loser_tuple,
            reason=reason.strip() if isinstance(reason, str) else "",
        ))
    return out


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _token_set(text: str) -> frozenset[str]:
    """Cheap tokenizer. Falls back to character grams for CJK/short text."""
    lowered = text.lower()
    tokens = _TOKEN_RE.findall(lowered)
    if len(tokens) >= 2:
        return frozenset(tokens)
    # Character bigrams as a fallback so two Chinese sentences with no
    # whitespace can still overlap.
    chars = [c for c in lowered if not c.isspace()]
    if len(chars) >= 2:
        return frozenset(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return frozenset(chars)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union)


def _recency_score(age_days: float) -> float:
    """Exponential decay with 90-day half-life. Always in [0, 1]."""
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / 90.0)


_DATE_RE = re.compile(r"\[[^,\]]+,\s*(\d{4}-\d{2}-\d{2})\]")


def _age_days_from_preference_line(
    text: str, *, now: datetime,
) -> float:
    """Best-effort age extraction from a rendered preference line.

    The preference store renders lines like ``- text [source, YYYY-MM-DD]``
    when listing entries; this returns 0 days when no date is present.
    """
    match = _DATE_RE.search(text)
    if not match:
        return 0.0
    try:
        ts = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
            tzinfo=timezone.utc,
        )
    except ValueError:
        return 0.0
    delta = (now - ts).total_seconds() / 86400.0
    return max(delta, 0.0)


def _format_diary_entry(report: ConsolidationReport) -> str:
    header = f"\n## {report.finished_at.isoformat()}\n"
    if report.error:
        return header + f"_skipped: {report.error}_\n"

    lines = [header]
    lines.append(
        f"_scanned {report.candidates_scanned} candidate(s)_\n",
    )
    if report.promoted:
        lines.append(f"\n**Promoted ({len(report.promoted)})**\n")
        for t in report.promoted:
            lines.append(f"- {t}\n")
    if report.consolidated:
        lines.append(f"\n**Consolidated ({len(report.consolidated)})**\n")
        for winner, losers in report.consolidated:
            losers_str = ", ".join(losers)
            lines.append(f"- {winner} ⟵ {losers_str}\n")
    if report.archived:
        lines.append(f"\n**Archived ({len(report.archived)})**\n")
        for t in report.archived:
            lines.append(f"- {t}\n")
    if not (report.promoted or report.consolidated or report.archived):
        lines.append("\n_no changes applied_\n")
    return "".join(lines)
