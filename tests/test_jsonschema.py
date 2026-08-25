"""In-tree JSON Schema subset: the keywords BEARING's own schemas actually use."""

from __future__ import annotations

import json
import os
import unittest

from context import PLUGIN_ROOT, SRC_ROOT, BearingTestCase

from bearing.jsonschema import validate
from bearing.util import read_json


class JsonSchemaSubsetTest(BearingTestCase):
    def test_required_and_additional_properties(self):
        schema = {
            "type": "object",
            "required": ["version"],
            "additionalProperties": False,
            "properties": {"version": {"const": 1}, "name": {"type": "string"}},
        }
        self.assertEqual(validate({"version": 1}, schema), [])
        self.assertTrue(any("missing" in error for error in validate({}, schema)))
        self.assertTrue(any("unknown key" in error for error in validate({"version": 1, "x": 1}, schema)))
        self.assertTrue(any("must equal" in error for error in validate({"version": 2}, schema)))

    def test_enum_and_type(self):
        schema = {"type": "string", "enum": ["a", "b"]}
        self.assertEqual(validate("a", schema), [])
        self.assertTrue(validate("c", schema))
        self.assertTrue(validate(1, schema))

    def test_local_ref(self):
        schema = {
            "type": "object",
            "properties": {"role": {"$ref": "#/$defs/role"}},
            "$defs": {"role": {"enum": ["cheap", "mid"]}},
        }
        self.assertEqual(validate({"role": "cheap"}, schema), [])
        self.assertTrue(validate({"role": "frontier"}, schema))

    def test_packaged_config_schema_accepts_defaults(self):
        schema = read_json(
            os.path.join(SRC_ROOT, "bearing", "data", "templates", "schemas", "config.schema.json")
        )
        defaults = read_json(os.path.join(SRC_ROOT, "bearing", "data", "config.default.json"))
        self.assertEqual(validate(defaults, schema), [])

    def test_candidate_schema_rejects_a_bare_object(self):
        schema = read_json(
            os.path.join(
                PLUGIN_ROOT, "skills", "decision-recovery", "schemas", "candidate.schema.json"
            )
        )
        errors = validate({"candidate_id": "x"}, schema)
        self.assertTrue(any("missing" in error for error in errors))
