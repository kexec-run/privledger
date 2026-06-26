from jsonschema import FormatChecker, validate


def validate_document(document: dict, schema: dict) -> None:
    """Validate a JSON document dict against a JSON Schema."""
    validate(instance=document, schema=schema, format_checker=FormatChecker())
