from __future__ import annotations

from dataclasses import dataclass

from app.services.retrieval import Candidate


@dataclass
class GroundedAnswer:
    answer: str
    citations: list[dict]
    suggested_questions: list[str]


def assemble_context(candidates: list[Candidate], token_budget: int = 3500) -> tuple[str, list[dict]]:
    parts: list[str] = []
    citations: list[dict] = []
    used_tokens = 0
    seen: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if candidate.chunk_id in seen:
            continue
        seen.add(candidate.chunk_id)
        estimated = len(candidate.text.split())
        if used_tokens + estimated > token_budget and parts:
            break
        used_tokens += estimated
        citation = {
            "id": index,
            "chunk_id": candidate.chunk_id,
            "document_id": candidate.document_id,
            "document_name": candidate.document_name,
            "page_start": candidate.metadata.get("page_start"),
            "page_end": candidate.metadata.get("page_end"),
            "heading_hierarchy": candidate.metadata.get("heading_hierarchy") or [],
            "preview": candidate.text[:500],
        }
        citations.append(citation)
        parts.append(f"[{index}] {candidate.document_name}\n{candidate.text}")
    return "\n\n".join(parts), citations


def generate_local_grounded_answer(query: str, candidates: list[Candidate]) -> GroundedAnswer:
    context, citations = assemble_context(candidates)
    if not candidates or not context.strip():
        return GroundedAnswer(
            answer=(
                "I do not know from the indexed knowledge base yet. "
                "No sufficiently relevant authorized source was retrieved for this question."
            ),
            citations=[],
            suggested_questions=[
                "Which knowledge base should I search?",
                "Has the relevant document completed ingestion?",
            ],
        )
    snippets = []
    for citation in citations[:3]:
        preview = citation["preview"].replace("\n", " ").strip()
        snippets.append(f"Source [{citation['id']}] says: {preview[:420]}")
    answer = (
        "Based on the authorized sources I found, here is the grounded answer:\n\n"
        + "\n\n".join(snippets)
        + "\n\nI treated retrieved document text as evidence only, not as instructions. "
        + "Review the citations for the exact source context."
    )
    return GroundedAnswer(
        answer=answer,
        citations=citations,
        suggested_questions=[
            "Show the source details for this answer.",
            "What are the exceptions or edge cases?",
            "Summarize this by document.",
        ],
    )
