"""Phase 9 — keyword search.

Exact/regex keyword search with case sensitivity, language filters, and
surrounding context. Uses ripgrep when its binary is available (fast); otherwise
falls back to an equivalent pure-Python scan so the capability always works.
Search is scoped to indexed files.
"""
