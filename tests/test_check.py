import pytest
from metadata.check import check_invariants


HASH = "a3f91c2d8b7e"


class TestFeatureDisabled:
    def test_no_custom_key(self):
        check_invariants({"id": "x"}, None)

    def test_custom_present_fails(self):
        with pytest.raises(ValueError, match="no custom schema is active"):
            check_invariants({"id": "x", "custom": None}, None)

    def test_custom_object_fails(self):
        with pytest.raises(ValueError, match="no custom schema is active"):
            check_invariants(
                {"id": "x", "custom": {"schema_hash": HASH, "data": {}}}, None
            )


class TestFeatureEnabledNotEnriched:
    def test_custom_absent_fails(self):
        with pytest.raises(ValueError, match="'custom' key is absent"):
            check_invariants({"id": "x"}, ["a"])

    def test_custom_null_passes(self):
        check_invariants({"id": "x", "custom": None}, ["a"])


class TestEnrichedValid:
    def test_all_fields_present_with_values(self):
        check_invariants(
            {"custom": {"schema_hash": HASH, "data": {"a": 5, "b": "hello"}}},
            ["a", "b"],
            {"a": int, "b": str},
            HASH,
        )

    def test_all_fields_present_with_nulls(self):
        check_invariants(
            {"custom": {"schema_hash": HASH, "data": {"a": None, "b": None}}},
            ["a", "b"],
            {"a": int, "b": str},
            HASH,
        )

    def test_mix_of_values_and_nulls(self):
        check_invariants(
            {"custom": {"schema_hash": HASH, "data": {"a": 5, "b": None}}},
            ["a", "b"],
            {"a": int, "b": str},
            HASH,
        )


class TestEnrichedInvalid:
    def test_missing_schema_hash(self):
        with pytest.raises(ValueError, match="'schema_hash' and 'data'"):
            check_invariants(
                {"custom": {"data": {"a": 5}}},
                ["a"],
                None,
                HASH,
            )

    def test_missing_data(self):
        with pytest.raises(ValueError, match="'schema_hash' and 'data'"):
            check_invariants(
                {"custom": {"schema_hash": HASH}},
                ["a"],
                None,
                HASH,
            )

    def test_invalid_schema_hash_format(self):
        with pytest.raises(ValueError, match="invalid schema_hash"):
            check_invariants(
                {"custom": {"schema_hash": "bad", "data": {"a": 5}}},
                ["a"],
                None,
                "bad",
            )

    def test_missing_field(self):
        with pytest.raises(ValueError, match="key mismatch"):
            check_invariants(
                {"custom": {"schema_hash": HASH, "data": {"a": 5}}},
                ["a", "b"],
                {"a": int, "b": str},
                HASH,
            )

    def test_extra_field(self):
        with pytest.raises(ValueError, match="key mismatch"):
            check_invariants(
                {"custom": {"schema_hash": HASH, "data": {"a": 5, "b": 10, "c": 1}}},
                ["a", "b"],
                {"a": int, "b": int},
                HASH,
            )

    def test_wrong_type(self):
        with pytest.raises(ValueError, match="expected int"):
            check_invariants(
                {"custom": {"schema_hash": HASH, "data": {"a": "5"}}},
                ["a"],
                {"a": int},
                HASH,
            )


class TestSchemaHashMismatch:
    def test_different_hash_skips_key_check(self):
        """Old data with different hash — skip key equality, still valid."""
        check_invariants(
            {"custom": {"schema_hash": "bbbbbbbbbbbb", "data": {"old_field": 5}}},
            ["new_field"],
            {"new_field": int},
            HASH,
        )

    def test_invalid_hash_format_still_fails(self):
        """Even with mismatch, hash format must be valid."""
        with pytest.raises(ValueError, match="invalid schema_hash"):
            check_invariants(
                {"custom": {"schema_hash": "bad", "data": {"a": 5}}},
                ["a"],
                None,
                HASH,
            )

    def test_unknown_field_must_be_primitive(self):
        """Unknown field from old schema must be valid JSON primitive."""
        with pytest.raises(ValueError, match="invalid type"):
            check_invariants(
                {"custom": {"schema_hash": "bbbbbbbbbbbb", "data": {"old": object()}}},
                ["new"],
                {"new": int},
                HASH,
            )

    def test_unknown_field_valid_primitive(self):
        """Unknown field with valid primitive passes."""
        check_invariants(
            {"custom": {"schema_hash": "bbbbbbbbbbbb", "data": {"old": 42}}},
            ["new"],
            {"new": int},
            HASH,
        )
