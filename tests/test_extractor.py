"""Tests for Tree-sitter symbol extraction."""

from __future__ import annotations

from code_intel.parsing.extractor import ParsedSymbol, SymbolExtractor


def _by_name(symbols: list[ParsedSymbol]) -> dict[str, ParsedSymbol]:
    return {s.name: s for s in symbols}


def test_python_functions_classes_and_methods() -> None:
    src = (
        b"CONST = 1\n"
        b"lower = 2\n\n"
        b"class Foo(Base):\n"
        b"    attr = 3\n"
        b"    def method(self, x):\n"
        b"        return x\n\n"
        b"def top(a):\n"
        b"    return a\n"
    )
    symbols = _by_name(SymbolExtractor().extract("Python", src))
    assert symbols["Foo"].type == "class"
    assert symbols["top"].type == "function"
    # A function nested in a class is reclassified as a method with a parent.
    assert symbols["method"].type == "method"
    assert symbols["method"].parent_id == symbols["Foo"].id
    # UPPER_CASE module-level assignment -> const; lowercase -> global.
    assert symbols["CONST"].type == "const"
    assert symbols["lower"].type == "global"
    # A class attribute is not emitted as a module global.
    assert "attr" not in symbols


def test_python_decorators_captured_and_normalised() -> None:
    src = (
        b"import functools\n\n"
        b"class C:\n"
        b"    @property\n"
        b"    def size(self):\n        return 1\n\n"
        b"    @staticmethod\n"
        b"    def helper():\n        return 2\n\n"
        b"@app.command('run')\n"
        b"def serve():\n    return 0\n\n"
        b"def plain():\n    return 3\n"
    )
    symbols = _by_name(SymbolExtractor().extract("Python", src))
    assert symbols["size"].decorators == ("property",)
    assert symbols["helper"].decorators == ("staticmethod",)
    # Call arguments are stripped; the dotted target is kept.
    assert symbols["serve"].decorators == ("app.command",)
    assert symbols["plain"].decorators == ()


def test_python_visibility_from_underscore() -> None:
    src = b"def _private():\n    pass\n\ndef public():\n    pass\n\ndef __dunder__():\n    pass\n"
    symbols = _by_name(SymbolExtractor().extract("Python", src))
    assert symbols["_private"].visibility == "private"
    assert symbols["public"].visibility == "public"
    assert symbols["__dunder__"].visibility == "public"


def test_line_numbers_are_one_based_and_span_body() -> None:
    src = b"def top(a):\n    return a\n"
    (sym,) = [s for s in SymbolExtractor().extract("Python", src) if s.name == "top"]
    assert sym.start_line == 1
    assert sym.end_line == 2
    assert sym.signature == "def top(a):"


def test_typescript_interface_enum_class_method() -> None:
    src = (
        b"interface I { a: number }\n"
        b"enum E { A, B }\n"
        b"class C implements I {\n  m(): void {}\n}\n"
        b"const g = (x: number) => x;\n"
    )
    symbols = _by_name(SymbolExtractor().extract("TypeScript", src))
    assert symbols["I"].type == "interface"
    assert symbols["E"].type == "enum"
    assert symbols["C"].type == "class"
    assert symbols["m"].type == "method"
    assert symbols["m"].parent_id == symbols["C"].id
    assert symbols["g"].type == "function"


def test_go_struct_interface_method_visibility() -> None:
    src = (
        b"package m\n"
        b"type S struct { X int }\n"
        b"type I interface { M() }\n"
        b"func (s S) Exported() {}\n"
        b"func unexported() {}\n"
    )
    symbols = _by_name(SymbolExtractor().extract("Go", src))
    assert symbols["S"].type == "struct"
    assert symbols["I"].type == "interface"
    assert symbols["Exported"].visibility == "public"
    assert symbols["unexported"].visibility == "private"


def test_rust_visibility_from_pub() -> None:
    src = b"pub fn exported() {}\nfn hidden() {}\npub struct S { x: i32 }\n"
    symbols = _by_name(SymbolExtractor().extract("Rust", src))
    assert symbols["exported"].visibility == "public"
    assert symbols["hidden"].visibility == "private"
    assert symbols["S"].type == "struct"


def test_unsupported_language_returns_empty() -> None:
    extractor = SymbolExtractor()
    assert extractor.supports("YAML") is False
    assert extractor.extract("YAML", b"a: 1\n") == []


def test_malformed_source_does_not_raise() -> None:
    # Truncated/invalid Python should degrade gracefully, never raise.
    result = SymbolExtractor().extract("Python", b"def broken(:\n  ???\n")
    assert isinstance(result, list)


def test_every_symbol_hashes_its_code() -> None:
    src = b"def a():\n    return 1\n\ndef b():\n    return 1\n"
    symbols = _by_name(SymbolExtractor().extract("Python", src))
    # Identical bodies but different names -> different code text -> different hash.
    assert symbols["a"].hash != symbols["b"].hash
    assert all(s.hash for s in symbols.values())
