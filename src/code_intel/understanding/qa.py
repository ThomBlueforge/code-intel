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
from code_intel.models import FileUnderstanding, RepoUnderstanding
from code_intel.retrieval.hybrid import HybridRetriever, RetrievalResult
from code_intel.storage.repositories import (
    FileUnderstandingStore,
    RepoUnderstandingStore,
    SymbolStore,
)
from code_intel.understanding.structural import StructuralAnswerer

_MAX_CONTEXT_SYMBOLS = 6
_MAX_CODE_CHARS = 1200
_MAX_TOTAL_CHARS = 9000  # room for the comprehension preamble + symbol blocks
_MAX_FILE_RESPONSIBILITIES = 8
_MAX_ARCHITECTURE_BULLETS = 6

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
        self._structural = StructuralAnswerer(conn, repository_id)
        # Bottom-up comprehension (Phase 23): repo overview + per-file
        # understanding, layered above the retrieved code so the model orients
        # itself the way an agent would. Empty until `enrich` has been run.
        self._file_understanding = FileUnderstandingStore(conn).map_for_repository(repository_id)
        self._repo_understanding = RepoUnderstandingStore(conn).get(repository_id)

    def ask(self, question: str, *, max_context: int = _MAX_CONTEXT_SYMBOLS) -> Answer:
        # Structural questions ("biggest file?", "longest function?", "where is
        # X?") are answered exactly from the symbol table — deterministic facts,
        # available with or without an LLM — before any retrieval guesswork.
        structural = self._structural.try_answer(question)
        if structural is not None:
            return Answer(question, structural.text, structural.citations, used_llm=False)

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

        # Preamble: the repository overview (what the project is, how it fits).
        overview = _format_repo_overview(self._repo_understanding)
        if overview:
            blocks.append(overview)
            total += len(overview)

        seen_files: set[str] = set()
        for i, result in enumerate(results):
            symbol = self._symbols.get(result.symbol_id)
            if symbol is None:
                continue
            # Once per file, show what that file does and its responsibilities.
            file_context = ""
            if symbol.path not in seen_files:
                seen_files.add(symbol.path)
                file_context = _format_file_understanding(self._file_understanding.get(symbol.path))
            summary = self._enriched.get(symbol.id, "")
            code = symbol.code[:_MAX_CODE_CHARS]
            block = (
                f"{file_context}"
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


def _format_repo_overview(repo: RepoUnderstanding | None) -> str:
    if repo is None:
        return ""
    architecture = "\n".join(
        f"  - {bullet}" for bullet in repo.architecture[:_MAX_ARCHITECTURE_BULLETS]
    )
    tail = f"\n{architecture}" if architecture else ""
    return f"Repository overview:\n{repo.summary}{tail}\n\n"


def _format_file_understanding(file: FileUnderstanding | None) -> str:
    if file is None:
        return ""
    responsibilities = "\n".join(
        f"    ({i + 1}) {item}"
        for i, item in enumerate(file.responsibilities[:_MAX_FILE_RESPONSIBILITIES])
    )
    tail = f"\n  Responsibilities:\n{responsibilities}" if responsibilities else ""
    return f"File `{file.path}` — {file.summary}{tail}\n"
