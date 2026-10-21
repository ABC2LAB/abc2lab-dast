"""Public, registered-request PoC recipes; never carry executed secrets or raw URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from abc2lab_contracts._validation import ContractRecord
from abc2lab_contracts.primitives import ParameterLocation, Ref, Revision, SourceVersion

_SLOT = re.compile(r"\$\{[A-Z][A-Z0-9_]*\}\Z")


@dataclass(frozen=True, slots=True)
class RecipeParameter(ContractRecord):
    """A path/query parameter identified by a registration-approved placeholder."""

    name: str
    location: ParameterLocation
    value_placeholder: str

    def _validate_invariants(self) -> None:
        if not self.name or any(char in self.name for char in "\r\n\x00"):
            raise ValueError("recipe parameter name must be non-empty and safe")
        if self.location not in (ParameterLocation.PATH, ParameterLocation.QUERY):
            raise ValueError("recipe parameters support only path/query")
        if _SLOT.fullmatch(self.value_placeholder) is None:
            raise ValueError("recipe parameter requires a placeholder slot")


@dataclass(frozen=True, slots=True)
class RegisteredRequestRecipe(ContractRecord):
    """An exportable GET template, not an executable or trusted request.

    Evidence/Report must independently match every template and slot against the
    injected registration. Shape validation alone never authorizes a request.
    """

    schema_version: str
    operation_ref: Ref
    operation_revision: Revision
    resource_ref: Ref
    resource_binding_ref: Ref
    resource_binding_revision: Revision
    method: str
    origin_placeholder: str
    path_template: str
    parameters: tuple[RecipeParameter, ...]
    authentication: str
    source: SourceVersion

    def _validate_invariants(self) -> None:
        if self.schema_version != "poc.v0.1":
            raise ValueError("unsupported recipe schema version")
        if self.method != "GET":
            raise ValueError("only registered GET recipes are exportable")
        if self.origin_placeholder != "${REGISTERED_ORIGIN}":
            raise ValueError("recipe origin must use the registered origin placeholder")
        if self.authentication != "fresh_registered_session":
            raise ValueError("recipe must use a fresh registered session")
        if (
            not self.path_template.startswith("/")
            or any(char in self.path_template for char in "\r\n\x00?#")
            or "://" in self.path_template
        ):
            raise ValueError("recipe path must be a registered path-only template")
        if len({(item.name, item.location) for item in self.parameters}) != len(self.parameters):
            raise ValueError("duplicate recipe parameter")
