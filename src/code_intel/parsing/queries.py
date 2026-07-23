"""Per-language Tree-sitter extraction queries.

Each entry maps a canonical language name (as produced by
``ingestion.languages``) to a ``(pack_name, query)`` pair, where ``pack_name``
is the grammar name understood by ``tree_sitter_language_pack`` and ``query`` is
a Tree-sitter query string.

Query convention: every definition pattern captures the whole definition node
as ``@kind.<symbol_type>`` and its identifier as ``@name``. The ``<symbol_type>``
suffix must be one of the canonical ``SYMBOL_TYPES``. These queries were
validated against real grammar output before being committed.

Languages without an entry are parsed by nobody: ingestion still records the
file, but no symbols are emitted (documented as a known limitation).
"""

from __future__ import annotations

# The bare (assignment ...) also matches class attributes and locals; the
# extractor keeps only parent-less (module-level) ones and promotes UPPER_CASE
# names to `const`.
_PYTHON = r"""
(function_definition name: (identifier) @name) @kind.function
(class_definition name: (identifier) @name) @kind.class
(assignment left: (identifier) @name) @kind.global
"""

_JAVASCRIPT = r"""
(function_declaration name: (identifier) @name) @kind.function
(class_declaration name: (identifier) @name) @kind.class
(method_definition name: (property_identifier) @name) @kind.method
(variable_declarator name: (identifier) @name value: (arrow_function)) @kind.function
"""

_TYPESCRIPT = r"""
(function_declaration name: (identifier) @name) @kind.function
(class_declaration name: (type_identifier) @name) @kind.class
(method_definition name: (property_identifier) @name) @kind.method
(interface_declaration name: (type_identifier) @name) @kind.interface
(enum_declaration name: (identifier) @name) @kind.enum
(variable_declarator name: (identifier) @name value: (arrow_function)) @kind.function
"""

_GO = r"""
(function_declaration name: (identifier) @name) @kind.function
(method_declaration name: (field_identifier) @name) @kind.method
(type_spec name: (type_identifier) @name type: (struct_type)) @kind.struct
(type_spec name: (type_identifier) @name type: (interface_type)) @kind.interface
(const_spec name: (identifier) @name) @kind.const
"""

_RUST = r"""
(function_item name: (identifier) @name) @kind.function
(struct_item name: (type_identifier) @name) @kind.struct
(trait_item name: (type_identifier) @name) @kind.trait
(enum_item name: (type_identifier) @name) @kind.enum
(const_item name: (identifier) @name) @kind.const
"""

_JAVA = r"""
(class_declaration name: (identifier) @name) @kind.class
(interface_declaration name: (identifier) @name) @kind.interface
(enum_declaration name: (identifier) @name) @kind.enum
(method_declaration name: (identifier) @name) @kind.method
"""

_C = r"""
(function_definition
  declarator: (function_declarator declarator: (identifier) @name)) @kind.function
(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @kind.struct
(enum_specifier name: (type_identifier) @name) @kind.enum
"""

_CPP = r"""
(function_definition
  declarator: (function_declarator declarator: (identifier) @name)) @kind.function
(class_specifier name: (type_identifier) @name) @kind.class
(struct_specifier name: (type_identifier) @name body: (field_declaration_list)) @kind.struct
(enum_specifier name: (type_identifier) @name) @kind.enum
(namespace_definition name: (namespace_identifier) @name) @kind.namespace
"""

_CSHARP = r"""
(class_declaration name: (identifier) @name) @kind.class
(interface_declaration name: (identifier) @name) @kind.interface
(struct_declaration name: (identifier) @name) @kind.struct
(enum_declaration name: (identifier) @name) @kind.enum
(method_declaration name: (identifier) @name) @kind.method
(namespace_declaration name: (identifier) @name) @kind.namespace
"""

_PHP = r"""
(function_definition name: (name) @name) @kind.function
(method_declaration name: (name) @name) @kind.method
(class_declaration name: (name) @name) @kind.class
(interface_declaration name: (name) @name) @kind.interface
(trait_declaration name: (name) @name) @kind.trait
(enum_declaration name: (name) @name) @kind.enum
"""

# Canonical language name -> (tree-sitter-language-pack grammar name, query).
LANGUAGE_QUERIES: dict[str, tuple[str, str]] = {
    "Python": ("python", _PYTHON),
    "JavaScript": ("javascript", _JAVASCRIPT),
    "TypeScript": ("typescript", _TYPESCRIPT),
    "Go": ("go", _GO),
    "Rust": ("rust", _RUST),
    "Java": ("java", _JAVA),
    "C": ("c", _C),
    "C++": ("cpp", _CPP),
    "C#": ("csharp", _CSHARP),
    "PHP": ("php", _PHP),
}


def parseable_languages() -> frozenset[str]:
    """Languages for which symbol extraction is implemented."""
    return frozenset(LANGUAGE_QUERIES)
