"""Report the trust ADR-0009's vocabulary introduces, from Rust source (VO-9, VO-10).

A proof is only as strong as what the author asked the verifier to accept
without argument. ADR-0009 fixes the vocabulary that does so; this package
finds it in real source, so the evidence gate can compare what a record claims
against what the code actually contains instead of trusting the record.

The package is split by what each part needs to know:

- :mod:`~docs_validation.trust_audit.lexer` separates code from comments and
  literals. It is the only module that must understand Rust's syntax.
- :mod:`~docs_validation.trust_audit.matcher` applies DL-17's matching rule to
  the lexed tokens, deciding which occurrences of a vocabulary word are trust.
- :mod:`~docs_validation.trust_audit.command` resolves module files against a
  repository root and renders the audit in the evidence schema's shape.

The split is deliberate: the rule can be tested over token streams with no
filesystem, and the filesystem policy can be tested with no Rust grammar beyond
``mod`` declarations.

Examples
--------
>>> scan('kani::assume(x > 0);').items
(TrustItem(item='assume', line=1, column=7),)
>>> scan('// kani::assume(x > 0);').items
()
"""
from .command import (
    AuditedFile,
    audit_tree,
    is_procedural_macro_crate,
    items_of,
    resolve_repository_path,
    scan_tree,
)
from .lexer import Kind, Token, TrustAuditError, literal_body, tokenize
from .matcher import (
    KANI_VOCABULARY,
    VERUS_VOCABULARY,
    VOCABULARY,
    ModuleReference,
    ScanResult,
    TrustItem,
    scan,
)

__all__ = [
    'KANI_VOCABULARY', 'VERUS_VOCABULARY', 'VOCABULARY', 'AuditedFile', 'Kind',
    'ModuleReference', 'ScanResult', 'Token', 'TrustAuditError', 'TrustItem',
    'audit_tree', 'is_procedural_macro_crate', 'items_of', 'literal_body',
    'resolve_repository_path', 'scan', 'scan_tree', 'tokenize',
]
