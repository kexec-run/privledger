from jsonschema import validate, FormatChecker


def validate_metadata(metadata: dict, schema: dict) -> None:
    """Validate metadata dict against schema. Raises on failure, returns None on success."""
    validate(instance=metadata, schema=schema, format_checker=FormatChecker())
