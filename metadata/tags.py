from pathlib import Path
from typing import cast

ROOT_DIR = Path(__file__).resolve().parent.parent
TAGS_PATH = ROOT_DIR / "config" / "tags.txt"


def load_tag_vocabulary(path: Path = TAGS_PATH) -> list[str]:
    """Load canonical tags in stable file order."""
    if not path.exists():
        return []

    tags: list[str] = []
    seen: set[str] = set()
    for line in path.read_text().splitlines():
        tag = line.strip()
        if not tag or tag.startswith("#"):
            continue
        if tag != tag.lower():
            raise ValueError(f"tag vocabulary contains non-lowercase tag: {tag}")
        if tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def load_tag_vocabulary_set(path: Path = TAGS_PATH) -> set[str]:
    return set(load_tag_vocabulary(path))


def normalize_tags_value(tags: object) -> list[object]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise TypeError("tags must be a list")
    return cast(list[object], tags)


def validate_regular_tags(tags: list[object], vocabulary: set[str]) -> None:
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("tags must contain strings")
        if tag != tag.lower():
            raise ValueError("tags must be lowercase")
        if vocabulary and tag not in vocabulary:
            raise ValueError("tags must exist in configured tag vocabulary")


def validate_focus_domain(
    focus_domain: object,
    regular_tags: list[str],
    vocabulary: set[str],
) -> None:
    if focus_domain is None:
        return
    if not isinstance(focus_domain, str):
        raise TypeError("focus_domain must be a string or null")
    if focus_domain != focus_domain.lower():
        raise ValueError("focus_domain must be lowercase")
    if vocabulary and focus_domain not in vocabulary:
        raise ValueError("focus_domain must be null or exist in configured tag vocabulary")
    if focus_domain in regular_tags:
        raise ValueError("focus_domain must not be duplicated in regular tags")


def validate_tag_bundle(
    tags: object,
    focus_domain: object,
    vocabulary: set[str] | None = None,
) -> list[str]:
    regular_tags = normalize_tags_value(tags)
    vocabulary = vocabulary if vocabulary is not None else load_tag_vocabulary_set()
    validate_regular_tags(regular_tags, vocabulary)
    validated_tags = cast(list[str], regular_tags)
    validate_focus_domain(focus_domain, validated_tags, vocabulary)
    return validated_tags
