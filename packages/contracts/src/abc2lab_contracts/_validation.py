"""Closed runtime validation for immutable C2 contract records."""

from __future__ import annotations

import re
import types
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Union, get_args, get_origin, get_type_hints


class ContractRecord:
    """Base for frozen, slot-based records with runtime invariant checks."""

    __slots__ = ()

    def __post_init__(self) -> None:
        # Only construction normalizes timestamps; fingerprint validation never mutates input.
        if not is_dataclass(self):
            raise TypeError("contract records must be dataclasses")
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is datetime:
                object.__setattr__(self, field.name, normalize_utc(value))
        validate_record(self)

    def _validate_invariants(self) -> None:
        """Validate record-specific invariants."""


def validate_record(record: object) -> None:
    """Validate one exact contract record and all declared nested values."""
    if not is_dataclass(record) or not isinstance(record, ContractRecord):
        raise TypeError("contract values must be ContractRecord instances")
    annotations = get_type_hints(type(record), include_extras=True)
    for field in fields(record):
        try:
            value = getattr(record, field.name)
        except AttributeError:
            raise TypeError("required contract field is missing") from None
        annotation = annotations.get(field.name)
        if annotation is None:
            raise TypeError("contract fields must have a declared annotation")
        _validate_value(field.name, value, annotation)
    record._validate_invariants()


def _validate_value(name: str, value: object, annotation: object) -> None:
    metadata: tuple[object, ...] = ()
    if get_origin(annotation) is Annotated:
        annotated_args = get_args(annotation)
        annotation = annotated_args[0]
        metadata = tuple(annotated_args[1:])
    if any(item == "opaque non-empty reference" for item in metadata):
        if type(value) is not str:
            raise TypeError(f"{name} must be a string reference")
        if not value:
            raise ValueError(f"{name} must be a non-empty reference")
        value.encode("utf-8", errors="strict")
        return
    if any(item == "positive revision" for item in metadata):
        if type(value) is not int:
            raise TypeError(f"{name} must be an integer revision")
        if value < 1:
            raise ValueError(f"{name} must be a positive revision")
        return
    if any(item == "timezone-aware UTC datetime" for item in metadata):
        if type(value) is not datetime:
            raise TypeError(f"{name} must be a datetime")
        normalize_utc(value)
        return

    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        if any(arg is type(None) and value is None for arg in get_args(annotation)):
            return
        if value is None:
            raise TypeError(f"{name} must not be None")
        for option in get_args(annotation):
            if option is type(None):
                continue
            try:
                _validate_value(name, value, option)
            except (TypeError, ValueError):
                continue
            return
        raise TypeError(f"{name} has an incompatible type")
    if origin is tuple:
        if type(value) is not tuple:
            raise TypeError(f"{name} must be a tuple")
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            for item in value:
                _validate_value(name, item, args[0])
        elif len(value) != len(args):
            raise TypeError(f"{name} has an invalid tuple length")
        else:
            for item, item_annotation in zip(value, args, strict=True):
                _validate_value(name, item, item_annotation)
        return
    if annotation is type(None):
        if value is not None:
            raise TypeError(f"{name} must be None")
        return
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not annotation:
            raise TypeError(f"{name} has an incompatible enum")
        return
    if annotation is bool:
        if type(value) is not bool:
            raise TypeError(f"{name} must be bool")
        return
    if annotation is int:
        if type(value) is not int:
            raise TypeError(f"{name} must be int")
        return
    if annotation is str:
        if type(value) is not str:
            raise TypeError(f"{name} must be str")
        value.encode("utf-8", errors="strict")
        return
    if annotation is datetime:
        if type(value) is not datetime:
            raise TypeError(f"{name} must be datetime")
        normalize_utc(value)
        return
    if isinstance(annotation, type) and issubclass(annotation, ContractRecord):
        if type(value) is not annotation:
            raise TypeError(f"{name} has an incompatible contract record")
        validate_record(value)
        return
    raise TypeError(f"{name} uses an unsupported contract annotation")


def normalize_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC without accepting naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def require_positive(name: str, value: object) -> None:
    """Require a positive integer setting without treating bool as an integer."""
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def require_fingerprint(value: str) -> None:
    """Require the documented lowercase SHA-256 representation."""
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("fingerprint must be lowercase SHA-256 hex")
