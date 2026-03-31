import re

_MISSING = object()


def check_invariants(data, custom_fields, custom_types=None, current_hash=None):
    """Enforce semantic invariants on a fully-constructed metadata object.

    Runs after schema validation, before write.
    Raises ValueError on any violation.

    custom_fields: list[str] | None  — field names (None = YAML disabled)
    custom_types: dict[str, type] | None  — field types (optional)
    current_hash: str | None  — current schema hash (optional)
    """
    custom = data.get("custom", _MISSING)

    # invariant 1: feature state
    if custom_fields is None:
        if custom is not _MISSING:
            raise ValueError("'custom' key present but no custom schema is active")
        return

    if custom is _MISSING:
        raise ValueError("custom schema is active but 'custom' key is absent")

    if custom is None:
        return  # STATE 1: not enriched, valid

    # invariant 2: envelope shape
    try:
        schema_hash = custom["schema_hash"]
        data_obj = custom["data"]
    except (TypeError, KeyError):
        raise ValueError("custom must contain 'schema_hash' and 'data'")

    if not isinstance(schema_hash, str) or not re.fullmatch(
        r"[0-9a-f]{12}", schema_hash
    ):
        raise ValueError("invalid schema_hash (must be 12-char hex string)")

    # invariant 3: schema alignment
    if schema_hash == current_hash:
        expected = set(custom_fields)
        actual = set(data_obj.keys())
        if actual != expected:
            missing = expected - actual
            extra = actual - expected
            parts = []
            if missing:
                parts.append(f"missing keys: {sorted(missing)}")
            if extra:
                parts.append(f"extra keys: {sorted(extra)}")
            raise ValueError(f"'custom.data' key mismatch — {', '.join(parts)}")

    # invariant 4: type validity
    if custom_types is not None:
        for k, v in data_obj.items():
            if v is None:
                continue
            expected_type = custom_types.get(k)
            if expected_type is not None:
                if not isinstance(v, expected_type):
                    raise ValueError(
                        f"'custom.data.{k}' expected {expected_type.__name__}, "
                        f"got {type(v).__name__}"
                    )
            else:
                if not isinstance(v, (int, float, str, bool)):
                    raise ValueError(
                        f"'custom.data.{k}' has invalid type {type(v).__name__}"
                    )
