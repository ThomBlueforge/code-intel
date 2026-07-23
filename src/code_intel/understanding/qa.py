"""Phase 12 — grounded question answering.

Assembles a bounded context from the hybrid retriever (never the whole repo),
then asks the LLM to answer using only that context, citing the specific symbols
used. With no LLM available it degrades to returning the ranked, cited context
so the command is still useful offline. The LLM never searches the repository —
all access goes through retrieval.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from code_intel.llm.client import ChatClient, ChatMessage, LLMError
from code_intel.retrieval.hybrid import HybridRetriever, RetrievalResult
from code_intel.storage.repositories import SymbolStore

_MAX_CONTEXT_SYMBOLS = 6
_MAX_CODE_CHARS = 1200
_MAX_TOTAL_CHARS = 7000

_SYSTEM = (
    "You are a code assistant. Answer the question using ONLY the provided "
    "context. Cite the sources you use by their [n] number. If the context is "
    "insufficient, say so plainly. Do not invent code or facts."
)


@dataclass(frozen=True)
class Answer:
    question: str
    answer: str
    citations: list[str]
    used_llm: bool


class QuestionAnswerer:
    """Answers questions about a repository, grounded in retrieved context."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        repository_id: str,
        retriever: HybridRetriever,
        chat_client: ChatClient | None = None,
    ) -> None:
        self._conn = conn
        self._repo_id = repository_id
        self._retriever = retriever
        self._chat = chat_client
        self._symbols = {s.id: s for s in SymbolStore(conn).list_for_repository(repository_id)}
        self._enriched = self._enriched_summaries()

    def ask(self, question: str, *, max_context: int = _MAX_CONTEXT_SYMBOLS) -> Answer:
        results = self._retriever.retrieve(question, limit=max_context)
        citations = [
            f"[{i + 1}] {r.path}:{r.start_line} {r.type} {r.name}"
            for i, r in enumerate(results)
        ]
        if not results:
            return Answer(question, "No relevant code found for this question.", [], False)

        context = self._build_context(results)
        if self._chat is not None:
            try:
                answer = self._chat.complete(
                    [
                        ChatMessage(role="system", content=_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=f"Context:\n{context}\n\nQuestion: {question}",
                        ),
                    ]
                )
                return Answer(question, answer.strip(), citations, used_llm=True)
            except LLMError:
                pass  # fall through to the deterministic answer

        return Answer(
            question,
            self._deterministic_answer(question, results),
            citations,
            used_llm=False,
        )

    def _build_context(self, results: list[RetrievalResult]) -> str:
        blocks: list[str] = []
        total = 0
        for i, result in enumerate(results):
            symbol = self._symbols.get(result.symbol_id)
            if symbol is None:
                continue
            summary = self._enriched.get(symbol.id, "")
            code = symbol.code[:_MAX_CODE_CHARS]
            block = (
                f"[{i + 1}] {symbol.path}:{symbol.start_line} {symbol.type} {symbol.name}\n"
                f"summary: {summary}\n"
                f"code:\n{code}\n"
            )
            if total + len(block) > _MAX_TOTAL_CHARS:
                break
            blocks.append(block)
            total += len(block)
        return "\n".join(blocks)

    def _deterministic_answer(self, question: str, results: list[RetrievalResult]) -> str:
        lines = [
            f"LLM not configured — returning the most relevant code for {question!r}:",
        ]
        for i, result in enumerate(results):
            summary = self._enriched.get(result.symbol_id, "")
            suffix = f" — {summary}" if summary else ""
            lines.append(f"  [{i + 1}] {result.type} {result.name} "
                         f"({result.path}:{result.start_line}){suffix}")
        return "\n".join(lines)

    def _enriched_summaries(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT symbol_id, summary FROM enriched_symbols WHERE summary != 'Unknown'"
        ).fetchall()
        return {row["symbol_id"]: row["summary"] for row in rows}
