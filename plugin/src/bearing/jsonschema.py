"""A validator for the JSON Schema subset BEARING's own schemas use.

@see ADR-0005 — this exists rather than a dependency so `bearing init` runs on
a bare Python 3.9.

Not a general-purpose implementation. It covers exactly the keywords used by
`config.schema.json`, `candidate.schema.json`, and `evidence.schema.json`:
type, enum, const, properties, additionalProperties, required, items,
minimum/maximum, minItems, pattern, $ref (local `#/$defs/...` only), oneOf and
anyOf.

The reason this exists rather than a dependency: config validation runs during
`bearing init` on a repository that has not installed anything yet. A validator
that needs `pip install` first is a validator that does not run when it matters.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def validate(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable error strings; empty means valid."""
    errors: List[str] = []
    _validate(instance, schema, schema, "", errors)
    return errors


def _resolve(schema: Dict[str, Any], root: Dict[str, Any]) -> Dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith("#/"):
        return schema
    cursor: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(cursor, dict) or part not in cursor:
            return schema
        cursor = cursor[part]
    merged = dict(cursor) if isinstance(cursor, dict) else schema
    for key, value in schema.items():
        if key != "$ref":
            merged[key] = value
    return merged


def _label(path: str) -> str:
    return path or "(root)"


def _check_type(instance: Any, expected: Any) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name == "number":
            if isinstance(instance, (int, float)) and not isinstance(instance, bool):
                return True
        elif name == "integer":
            if isinstance(instance, int) and not isinstance(instance, bool):
                return True
        elif name == "boolean":
            if isinstance(instance, bool):
                return True
        elif name in _TYPES:
            if isinstance(instance, _TYPES[name]) and not (
                name != "boolean" and isinstance(instance, bool) and _TYPES[name] is not bool
            ):
                return True
    return False


def _validate(
    instance: Any,
    schema: Dict[str, Any],
    root: Dict[str, Any],
    path: str,
    errors: List[str],
) -> None:
    if not isinstance(schema, dict):
        return
    schema = _resolve(schema, root)

    if "const" in schema and instance != schema["const"]:
        errors.append("%s must equal %r (found %r)" % (_label(path), schema["const"], instance))
        return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(
            "%s must be one of %s (found %r)"
            % (_label(path), ", ".join(repr(item) for item in schema["enum"]), instance)
        )
        return

    for combiner in ("oneOf", "anyOf"):
        if combiner in schema:
            branches = schema[combiner]
            if not any(not _branch_errors(instance, branch, root, path) for branch in branches):
                errors.append("%s did not match any permitted form of %s" % (_label(path), combiner))
                return

    if "type" in schema and not _check_type(instance, schema["type"]):
        expected = schema["type"]
        expected_text = expected if isinstance(expected, str) else " or ".join(expected)
        errors.append(
            "%s must be %s (found %s)" % (_label(path), expected_text, type(instance).__name__)
        )
        return

    if isinstance(instance, dict):
        _validate_object(instance, schema, root, path, errors)
    elif isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                _validate(item, item_schema, root, "%s[%d]" % (_label(path), index), errors)
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            errors.append("%s must have at least %d item(s)" % (_label(path), min_items))
    elif isinstance(instance, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and not re.search(pattern, instance):
            errors.append("%s must match pattern %s" % (_label(path), pattern))
    elif isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            errors.append("%s must be >= %s (found %s)" % (_label(path), minimum, instance))
        if isinstance(maximum, (int, float)) and instance > maximum:
            errors.append("%s must be <= %s (found %s)" % (_label(path), maximum, instance))


def _validate_object(
    instance: Dict[str, Any],
    schema: Dict[str, Any],
    root: Dict[str, Any],
    path: str,
    errors: List[str],
) -> None:
    properties = schema.get("properties") or {}
    for key in schema.get("required") or []:
        if key not in instance:
            errors.append("%s is missing required key %r" % (_label(path), key))

    if schema.get("additionalProperties") is False:
        allowed = set(properties) | {"$schema"}
        for key in sorted(instance):
            if key not in allowed:
                errors.append(
                    "%s has unknown key %r (permitted: %s)"
                    % (_label(path), key, ", ".join(sorted(properties)) or "none")
                )

    for key, value in instance.items():
        if key in properties:
            child = "%s.%s" % (path, key) if path else key
            _validate(value, properties[key], root, child, errors)


def _branch_errors(
    instance: Any, schema: Dict[str, Any], root: Dict[str, Any], path: str
) -> List[str]:
    collected: List[str] = []
    _validate(instance, schema, root, path, collected)
    return collected
