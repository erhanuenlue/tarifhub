"""The commentary-search tool: the one read-only tool of the evidence-seeking agent (offline).

A model that has received the fixed retrieval's passages for a question may ask for more. This
module runs one such search request entirely in code: the model's arguments are only a query,
what it is seeking and, optionally, editions; the ranking method, the window and the limits are
fixed here (ADR-026). A search ranks the passages of the editions selected for the question
with the pilot's hybrid ranking and returns, from its fixed top window, passages the model has
not been given yet, rendered as the same escaped, untrusted ``<passage>`` data as the fixed
context. It reads only the in-memory corpus: no tariff database, no network, no model call.

``search_commentary`` takes the state of one question and returns the next state with the
result; it never changes its inputs. The result's ``record`` holds structured metadata only
(outcome, round, editions, passage IDs, ranks, scores, hashes, counts) and may be published;
``local`` holds the raw arguments and error text, and ``content`` (the tool result for the
model) carries passage text: both stay in local artifacts, as passage text does in the pilot.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass, replace

import corpus
import generation

METHOD = "hybrid"  # the pilot's ranking for the fixed context (ADR-025), fixed for every search


@dataclass(frozen=True)
class SearchLimits:
    """The bounds of the searches for one question."""

    max_rounds: int = 2  # search requests per question, refused ones included
    max_passages: int = 10  # distinct passages supplied per question, the fixed five included
    per_search: int = 5  # new passages one search may return
    window: int = 10  # the top of the ranking a search returns passages from
    max_query_chars: int = 200
    max_seeking_chars: int = 300


@dataclass(frozen=True)
class SearchState:
    """One question's searches so far: its editions, the passages supplied, rounds used."""

    permitted: tuple[str, ...]  # the editions selected for the question
    supplied: tuple[str, ...]  # passage IDs given to the model, in the order given
    rounds_used: int = 0
    searched: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (folded query, editions) ranked


@dataclass(frozen=True)
class SearchResult:
    """What one search request produced, and the question's state after it."""

    outcome: str
    is_error: bool
    content: str  # the tool result for the model; carries passage text, local artifacts only
    passages: tuple[str, ...]  # the new passages returned, best first
    state: SearchState
    record: dict  # structured metadata, publishable
    local: dict  # raw arguments and error text, local artifacts only


def search_commentary(arguments, state: SearchState, *, retriever,
                      passages: Mapping[str, Mapping], limits: SearchLimits) -> SearchResult:
    """Run one search request for a question in ``state``; return its result and next state."""

    if state.rounds_used >= limits.max_rounds:  # no round left to use: the state stays as is
        return _refused(state, "refused_rounds", f"this question has used its "
                        f"{limits.max_rounds} searches", arguments, limits, counted=False)
    used = replace(state, rounds_used=state.rounds_used + 1)  # every later outcome uses a round
    if len(state.supplied) >= limits.max_passages:
        return _refused(used, "refused_passage_budget", "this question already has the most "
                        f"passages it may receive ({limits.max_passages})", arguments, limits)
    if not _well_formed(arguments, limits):
        return _refused(used, "refused_arguments", "the arguments must be query (1 to "
                        f"{limits.max_query_chars} characters), seeking (1 to "
                        f"{limits.max_seeking_chars} characters) and, optionally, editions "
                        "(a list of edition dates), nothing else", arguments, limits)
    requested = arguments.get("editions")
    if requested is not None and (not requested or any(e not in state.permitted
                                                       for e in requested)):
        return _refused(used, "refused_editions", "editions must be a non-empty selection from "
                        f"the editions selected for this question ({', '.join(state.permitted)})",
                        arguments, limits)
    editions = [e for e in state.permitted if requested is None or e in requested]
    key = (corpus.normalize(arguments["query"]).casefold(), tuple(editions))
    if key in state.searched:
        return _refused(used, "refused_repeat", "this search repeats an earlier one (the same "
                        "query over the same editions); search for something else", arguments,
                        limits)
    try:
        return _ranked(arguments, replace(used, searched=(*state.searched, key)), editions,
                       retriever=retriever, passages=passages, limits=limits)
    except Exception as exc:  # noqa: BLE001 - any failure of the search is reported, not raised
        record = _record(used, "tool_error", limits)
        content = ("Search failed: this search could not be run and returned no passages. "
                   f"Searches left: {record['rounds_left']}; passages left: "
                   f"{record['passages_left']}.")
        return SearchResult(outcome="tool_error", is_error=True, content=content, passages=(),
                            state=used, record=record,
                            local={"arguments": arguments,
                                   "error": f"{type(exc).__name__}: {exc}"})


def _ranked(arguments, used: SearchState, editions: list[str], *, retriever,  # noqa: PLR0913
            passages: Mapping[str, Mapping], limits: SearchLimits) -> SearchResult:
    """Rank the selected editions and return the best unseen passages of the window.

    ``used`` is the state with this round counted; its ``supplied`` is still the earlier list.
    """

    ranking = retriever.rank(arguments["query"], method=METHOD, editions=editions)
    window = [(rank, hit) for rank, hit in enumerate(ranking[:limits.window], start=1)]
    capacity = min(limits.per_search, limits.max_passages - len(used.supplied))
    new = [(rank, hit) for rank, hit in window if hit.passage_id not in used.supplied][:capacity]
    seen = [hit.passage_id for _, hit in window if hit.passage_id in used.supplied]
    returned = tuple(hit.passage_id for _, hit in new)
    outside = [pid for pid in returned if passages[pid]["edition"] not in editions]
    if outside:  # the records disagree with the ranked corpus: nothing goes to the model
        raise ValueError(f"passage record(s) outside the selected editions: {', '.join(outside)}")
    after = replace(used, supplied=used.supplied + returned)
    outcome = "passages" if returned else "no_new_passages"
    record = {**_record(after, outcome, limits), "editions": editions, "already_supplied": seen,
              "returned": [{"passage_id": hit.passage_id, "rank": rank, "score": hit.score,
                            "edition": passages[hit.passage_id]["edition"],
                            "page": passages[hit.passage_id]["page"],
                            "section": passages[hit.passage_id]["section"],
                            "text_sha256": passages[hit.passage_id]["text_sha256"]}
                           for rank, hit in new]}
    body = "\n".join(generation._passage(passages[pid]) for pid in returned)
    note = "" if returned else (f"No new passages: every passage among the top {limits.window} "
                                "of this search was already supplied.\n")
    content = (
        f'<suchergebnis runde="{after.rounds_used}" verbleibende_suchen="{record["rounds_left"]}" '
        f'verbleibende_passagen="{record["passages_left"]}">\n{note}<passagen>\n{body}\n'
        f"</passagen>\n<bereits_geliefert>{html.escape(' '.join(seen), quote=False)}"
        "</bereits_geliefert>\n</suchergebnis>"
    )
    return SearchResult(outcome=outcome, is_error=False, content=content, passages=returned,
                        state=after, record=record, local={"arguments": arguments})


def _well_formed(arguments, limits: SearchLimits) -> bool:
    """Exactly a query, what is sought and optionally a list of editions, each within limits."""

    if not isinstance(arguments, Mapping) or set(arguments) - {"query", "seeking", "editions"}:
        return False

    def text(key: str, most: int) -> bool:  # the whole string is bounded: it is what is ranked
        value = arguments.get(key)
        return isinstance(value, str) and bool(value.strip()) and len(value) <= most

    editions = arguments.get("editions", [])
    return (text("query", limits.max_query_chars) and text("seeking", limits.max_seeking_chars)
            and isinstance(editions, list) and all(isinstance(e, str) for e in editions))


def _record(state: SearchState, outcome: str, limits: SearchLimits, *,
            counted: bool = True) -> dict:
    """The publishable metadata of one search request: no query, seeking or error text.

    A request that ranked nothing has no editions, returned or already-supplied passages.
    """

    return {"round": state.rounds_used if counted else None, "outcome": outcome, "method": METHOD,
            "editions": None, "window": limits.window, "returned": [], "already_supplied": [],
            "rounds_left": limits.max_rounds - state.rounds_used,
            "passages_left": limits.max_passages - len(state.supplied)}


def _refused(state: SearchState, outcome: str, reason: str, arguments,  # noqa: PLR0913
             limits: SearchLimits, *, counted: bool = True) -> SearchResult:
    """A request that is not run: nothing is ranked or returned; ``state`` is already final.

    ``counted`` is False only when no round was left to use, so the request has no round.
    """

    record = _record(state, outcome, limits, counted=counted)
    content = (f"Search refused: {reason}. Searches left: {record['rounds_left']}; "
               f"passages left: {record['passages_left']}.")
    return SearchResult(outcome=outcome, is_error=True, content=content, passages=(),
                        state=state, record=record, local={"arguments": arguments})
