#!/usr/bin/env python3
"""Check spec/schemas/ard.cddl with whichever CDDL tools are installed.

Two independent implementations are supported, and every test runs against each
one found, because they disagree on edge cases (the Ruby tool rejected nested group
choices, the Rust tool read a bare `uri:` key as the prelude type):

- the reference Ruby tool (`gem install cddl`), found as CDDL_RB or a `cddl` without a
  `compile-cddl` subcommand;
- the Rust tool (`cargo install cddl`), found as CDDL_RS or a `cddl` with one.

Both install a binary named `cddl`, so every `cddl` on PATH is probed, plus the
default cargo and gem locations, and one shadowing the other is still found.

With neither installed the tests skip, so the zero-dependency suite still passes.

The Ruby tool runs with support/cddl_rb_group_choice.rb loaded, which fixes its crash
on a group choice inside a named or unwrapped group (gem 0.12.14 only).
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CDDL_FILE = REPO_ROOT / "spec" / "schemas" / "ard.cddl"
AI_CATALOG_CDDL = REPO_ROOT / "spec" / "schemas" / "ai-catalog.cddl"

# The Rust tool rejects every map built with ~ (anweiss/cddl #65 behaviour, still on
# main at 3471fdc), so rules whose maps unwrap CatalogEntry are checked by the Ruby
# tool only.
UNWRAP_RULES = {"search-response", "search-result-item", "list-response", "list-item"}
SPEC_FILE = REPO_ROOT / "spec" / "ard.md"
EXAMPLES = sorted((REPO_ROOT / "conformance" / "examples").glob("**/*.json"))
VALID_ID = "urn:air:example.com:finance/agent:mcp"
RUBY_SUPPORT = Path(__file__).resolve().parent / "support"


def _run(kind, command, timeout):
    env = os.environ.copy()
    if kind == "ruby":
        # RUBYOPT splits on whitespace, so the patch goes on RUBYLIB by directory and
        # is required by name, which works from a checkout whose path has a space.
        env["RUBYLIB"] = os.pathsep.join(p for p in (str(RUBY_SUPPORT), env.get("RUBYLIB", "")) if p)
        env["RUBYOPT"] = f"{env.get('RUBYOPT', '')} -rcddl_rb_group_choice".strip()
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)


def _candidates():
    yield os.environ.get("CDDL_RB")
    yield os.environ.get("CDDL_RS")
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        yield os.path.join(directory, "cddl")
    yield os.path.expanduser("~/.cargo/bin/cddl")
    yield from (str(path) for path in Path.home().glob(".gem/ruby/*/bin/cddl"))
    try:
        bindir = subprocess.run(["gem", "environment", "bindir"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        bindir = ""
    if bindir:
        yield os.path.join(bindir, "cddl")


def _find_tools():
    tools = {}
    for path in _candidates():
        if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
            continue
        try:
            out = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        kind = "rust" if "compile-cddl" in out.stdout + out.stderr else "ruby"
        tools.setdefault(kind, path)
    return tools


TOOLS = _find_tools()


def _grammar(start):
    text = CDDL_FILE.read_text(encoding="utf-8")
    text = re.sub(r"^start = .*$", f"start = {start}", text, count=1, flags=re.M)
    # AI Catalog types updatedAt as tdate, which RFC 8610 defines as CBOR tag 0 around
    # a string. JSON has no tags, so for the JSON instances checked here a tdate is its
    # string; the Ruby tool otherwise rejects every JSON updatedAt.
    catalog = re.sub(r"\btdate\b", "tstr", AI_CATALOG_CDDL.read_text(encoding="utf-8"))
    return text + "\n" + catalog


_COMPILED = {}


def _compile(kind, grammar):
    """Fail the test, not just the instance, when the tool can't process the grammar."""
    key = (kind, grammar.read_text(encoding="utf-8"))
    if key not in _COMPILED:
        if kind == "rust":
            command = [TOOLS[kind], "compile-cddl", "--cddl", str(grammar)]
        else:
            command = [TOOLS[kind], str(grammar), "generate"]
        result = _run(kind, command, 60)
        _COMPILED[key] = (result.returncode == 0, result.stdout + result.stderr)
    compiled, output = _COMPILED[key]
    if not compiled:
        raise AssertionError(f"{kind} cddl could not compile the grammar:\n{output}")


def _validate(kind, start, document):
    return _validate_grammar(kind, _grammar(start), document)


def _validate_grammar(kind, text, document):
    with tempfile.TemporaryDirectory() as temp_dir:
        grammar = Path(temp_dir) / "ard.cddl"
        grammar.write_text(text, encoding="utf-8")
        _compile(kind, grammar)
        instance = Path(temp_dir) / "instance.json"
        instance.write_text(json.dumps(document), encoding="utf-8")
        if kind == "rust":
            command = [TOOLS[kind], "validate", "--cddl", str(grammar), "--json", str(instance)]
        else:
            command = [TOOLS[kind], str(grammar), "validate", str(instance)]
        result = _run(kind, command, 30)
    output = result.stdout + result.stderr
    # The Rust tool exits 0 either way, so both tools are read by their messages.
    if kind == "rust":
        valid = "is successful" in output
        rejected = "failed: error validating" in output
    else:
        valid = result.returncode == 0
        rejected = result.returncode != 0 and "CDDL validation failure" in output
    if valid == rejected:
        raise AssertionError(f"{kind} cddl neither accepted nor rejected the instance:\n{output}")
    return valid, output


def _entry(**members):
    entry = {
        "identifier": VALID_ID,
        "displayName": "Fixture",
        "type": "application/mcp-server-card+json",
        "url": "https://example.com/mcp.json",
    }
    entry.update(members)
    return entry


def _api_examples():
    """The JSON examples in §5.3 and §5.4, each with the rule it is an instance of."""
    spec = SPEC_FILE.read_text(encoding="utf-8")
    section = spec[spec.index("### 5.3 The Search API"):spec.index("### 5.5")]
    for block in re.findall(r"```json\n(.*?)```", section, re.S):
        document = json.loads(block)
        if "results" in document:
            yield "search-response", document
        elif isinstance(document.get("resultType"), str):
            yield "explore-response", document
        elif isinstance(document.get("resultType"), dict):
            yield "explore-request", document
        else:
            yield "search-request", document


@unittest.skipUnless(TOOLS, "no CDDL tool installed (gem install cddl, or cargo install cddl)")
class CddlTests(unittest.TestCase):
    def _kinds(self, start, tools=None):
        kinds = [kind for kind in (tools or TOOLS) if kind in TOOLS]
        if start in UNWRAP_RULES:
            kinds = [kind for kind in kinds if kind != "rust"]
        if not kinds:
            self.skipTest(f"no installed cddl tool can check {start} (found {', '.join(sorted(TOOLS))})")
        return kinds

    def assert_valid(self, start, document):
        for kind in self._kinds(start):
            with self.subTest(tool=kind):
                valid, output = _validate(kind, start, document)
                self.assertTrue(valid, output)

    def assert_invalid(self, start, document, tools=None):
        for kind in self._kinds(start, tools):
            with self.subTest(tool=kind):
                valid, output = _validate(kind, start, document)
                self.assertFalse(valid, output)

    def test_examples_validate(self):
        self.assertTrue(EXAMPLES)
        for path in EXAMPLES:
            with self.subTest(example=path.name):
                self.assert_valid("ard-manifest", json.loads(path.read_text(encoding="utf-8")))

    def test_spec_api_examples_validate(self):
        examples = list(_api_examples())
        self.assertGreaterEqual(len(examples), 5)
        for start, document in examples:
            with self.subTest(rule=start):
                self.assert_valid(start, document)

    def test_entry_with_data_validates(self):
        entry = _entry()
        del entry["url"]
        entry["data"] = {"name": "inline"}
        self.assert_valid("ard-entry", entry)

    def test_attestation_uri_is_a_key(self):
        manifest = {"type": "SOC2-Type2", "uri": "https://example.com/soc2.pdf"}
        self.assert_valid("attestation", manifest)
        self.assert_invalid("attestation", {"type": "SOC2-Type2"})

    def test_empty_tags_and_capabilities_validate(self):
        self.assert_valid("ard-entry", _entry(tags=[], capabilities=[]))

    def test_context_forms(self):
        for context in ("https://agenticresourcediscovery.org/context/v1", {"okf": "https://openknowledgeformat.org/ns#"}, []):
            with self.subTest(context=context):
                self.assert_valid("ard-entry", _entry(**{"@context": context}))
        self.assert_invalid("ard-entry", _entry(**{"@context": 7}))

    def test_explore_query_accepts_context(self):
        request = {
            "query": {"@context": {"okf": "https://openknowledgeformat.org/ns#"}, "filter": {"okf:taxonomy": ["us-gaap"]}},
            "resultType": {"facets": [{"field": "type"}]},
        }
        self.assert_valid("explore-request", request)

    def test_search_query_requires_text(self):
        self.assert_invalid("search-request", {"query": {"filter": {"type": ["application/mcp-server-card+json"]}}})

    def test_facet_bucket_count_is_optional(self):
        self.assert_valid("explore-response", {"resultType": "facets", "facets": {"type": {"buckets": [{"value": "x"}]}}})

    def test_page_size_is_at_most_100(self):
        self.assert_valid("search-request", {"query": {"text": "x"}, "pageSize": 100})
        self.assert_invalid("search-request", {"query": {"text": "x"}, "pageSize": 101})

    def test_referral_is_open(self):
        referral = {
            "identifier": "urn:air:example.com:registry/travel",
            "displayName": "Travel",
            "type": "application/ai-registry+json",
            "url": "https://travel.example/search",
            "description": "Travel agents",
        }
        self.assert_valid("registry-referral", referral)

    def test_group_choice_inside_a_named_group(self):
        # The shape that crashed the unpatched Ruby tool, from its own test_murray.
        grammar = "start = a\na = { b }\nb = ( (x: int // y: int), z: int )\n"
        cases = [({"x": 2, "z": 1}, True), ({"y": 1, "z": 2}, True), ({"z": 1}, False), ({}, False)]
        for kind in TOOLS:
            for document, expected in cases:
                with self.subTest(tool=kind, document=document):
                    valid, output = _validate_grammar(kind, grammar, document)
                    self.assertEqual(valid, expected, output)

    def test_result_is_a_complete_catalog_entry(self):
        result = dict(_entry(), score=95, source="https://registry.example/")
        self.assert_valid("search-result-item", result)
        self.assert_valid("search-result-item", dict(result, updatedAt="2026-03-15T10:00:00Z", version="1.0.0"))
        inline = {k: v for k, v in result.items() if k != "url"}
        self.assert_valid("search-result-item", dict(inline, data={"name": "inline"}))
        self.assert_invalid("search-result-item", {"identifier": VALID_ID, "score": 95, "source": "https://r/"})
        self.assert_invalid("search-result-item", inline)
        # CatalogEntry's wildcard admits the second member; OpenAPI's oneOf rejects it.
        self.assert_valid("search-result-item", dict(result, data={"name": "inline"}))
        self.assert_invalid("search-result-item", dict(result, score="high"))
        self.assert_invalid("search-result-item", {k: v for k, v in result.items() if k != "source"})

    def test_result_types_ard_terms(self):
        result = dict(_entry(), score=95, source="https://registry.example/")
        self.assert_valid("search-result-item", dict(result, capabilities=["WeatherTool"], **{"okf:taxonomy": "x"}))
        self.assert_invalid("search-result-item", dict(result, capabilities="WeatherTool"))
        self.assert_invalid("search-result-item", dict(result, trustManifest={"attestations": []}))

    def test_list_items_are_catalog_entries(self):
        self.assert_valid("list-response", {"items": [_entry(), _entry(version="2.0.0")], "total": 2})
        self.assert_invalid("list-response", {"items": [{"identifier": VALID_ID}]})

    def test_identifier_pattern(self):
        for identifier in ("urn:air:example.com:weather", VALID_ID, "urn:air:example.com:a%2Fb"):
            with self.subTest(identifier=identifier):
                self.assert_valid("ard-entry", _entry(identifier=identifier))
        # The Rust tool doesn't anchor .regexp, so only the reference tool can reject these.
        for identifier in ("urn:air:example.com:a:b:c", "urn:air:example.com", "https://example.com/agent"):
            with self.subTest(identifier=identifier):
                self.assert_invalid("ard-entry", _entry(identifier=identifier), tools=("ruby",))


if __name__ == "__main__":
    unittest.main()
