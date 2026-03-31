import hashlib

import yaml

TYPE_MAP = {
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "string": str,
}

VALID_TYPES = set(TYPE_MAP.keys())


def load_custom_schema(path):
    """Load, validate, and normalize a custom schema YAML file.

    Returns (fields, types, schema_hash) where:
        fields: sorted list of field names
        types: field_name -> python type
        schema_hash: 12-char hex hash of canonical schema

    Raises ValueError on any validation failure.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    # invariant 1: structure
    if not isinstance(raw, dict):
        raise ValueError("custom schema must be a mapping")

    # normalize + validate
    fields = {}
    for k, v in raw.items():
        key = normalize_name(k)
        typ = normalize_type(v)

        if key in fields:
            raise ValueError(f"duplicate field: {key}")

        fields[key] = typ

    # invariant 3: bounded size
    if not (1 <= len(fields) <= 10):
        raise ValueError("schema must have 1-10 fields")

    # invariant 2: canonical form
    items = sorted(fields.items())
    canonical = "|".join(f"{k}:{v}" for k, v in items)

    schema_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]

    return (
        [k for k, _ in items],
        {k: TYPE_MAP[v] for k, v in items},
        schema_hash,
    )


def normalize_name(name):
    """Normalize and validate a field name."""
    if not isinstance(name, str):
        raise ValueError("field name must be string")

    name = name.strip().lower()

    if not name:
        raise ValueError("empty field name")

    if " " in name:
        raise ValueError(f"invalid field '{name}', use '_' instead")

    if not name.replace("_", "").isalnum():
        raise ValueError(f"invalid field '{name}'")

    if name[0].isdigit():
        raise ValueError(f"field '{name}' cannot start with number")

    return name


def normalize_type(t):
    """Normalize and validate a type string."""
    if not isinstance(t, str):
        raise ValueError("type must be string")

    t = t.strip().lower()

    if t not in VALID_TYPES:
        raise ValueError(f"invalid type '{t}'")

    return t
