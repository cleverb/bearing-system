"""MCP App preview: catalog, fixtures, HTML injection, and `bearing ui-preview --list`."""

from __future__ import annotations

import json
import os
import unittest
from urllib.request import urlopen

from context import BearingTestCase, run_cli
from bearing.paths import data_dir
from bearing.ui_preview import (
    REQUIRED_STORY_IDS,
    PreviewSession,
    catalog_issues,
    default_catalog_path,
    default_fixtures_dir,
    inject_app_html,
    load_catalog,
    start_background,
    story_by_id,
    story_fixture_paths,
)
from bearing.util import read_json


def _html_root():
    return data_dir()


def _catalog_path():
    return default_catalog_path(_html_root())


class CatalogAndFixturesTest(BearingTestCase):
    def test_required_stories_exist_and_fixtures_validate(self):
        path = _catalog_path()
        catalog = load_catalog(path)
        issues = catalog_issues(catalog, path, default_fixtures_dir(_html_root()))
        self.assertEqual(issues, [])
        ids = {story["id"] for story in catalog["stories"]}
        for required in REQUIRED_STORY_IDS:
            self.assertIn(required, ids)

    def test_readme_tells_authors_to_add_a_story(self):
        readme = os.path.join(_html_root(), "ui-preview", "README.md")
        with open(readme, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("catalog.json", text)
        self.assertIn("add or extend a catalog story", text.lower())


class InjectionAndRpcTest(BearingTestCase):
    def test_inject_replaces_boot_and_icon_sprite(self):
        html = inject_app_html(
            "recovery", {"run_id": "preview-test", "status": "running"}, _html_root()
        )
        self.assertIn("preview-test", html)
        self.assertNotIn("<!-- BEARING:ICONS -->", html)
        self.assertIn('id="icon-file"', html)
        self.assertIn('id="boot"', html)

    def test_preview_session_resources_and_tools(self):
        catalog = load_catalog(_catalog_path())
        story = story_by_id(catalog, "review-few")
        catalog_dir = os.path.dirname(_catalog_path())
        paths = story_fixture_paths(story, catalog_dir, default_fixtures_dir(_html_root()))
        fixtures = [read_json(path, {}) for path in paths]
        session = PreviewSession(story, fixtures)
        listed = session.handle_rpc("tools/call", {"name": "list_reviewable", "arguments": {}})
        self.assertFalse(listed.get("isError"))
        self.assertGreater(listed["structuredContent"]["count"], 0)
        first = listed["structuredContent"]["candidates"][0]["candidate_id"]
        pending = session.handle_rpc(
            "tools/call",
            {"name": "review_candidate", "arguments": {"candidate_id": first}},
        )
        self.assertEqual(pending["structuredContent"]["status"], "needs_disposition")
        promoted = session.handle_rpc(
            "tools/call",
            {
                "name": "review_candidate",
                "arguments": {
                    "candidate_id": first,
                    "disposition": {
                        "action": "Promote",
                        "still_valid": True,
                        "scope": "plugin/src/bearing/*.py",
                    },
                },
            },
        )
        self.assertEqual(promoted["structuredContent"]["status"], "disposed")

    def test_http_serves_injected_app_and_host_clock_controls(self):
        url, httpd, _thread = start_background(
            _catalog_path(),
            _html_root(),
            default_fixtures_dir(_html_root()),
            port=0,
        )
        try:
            host = urlopen(url).read().decode("utf-8")
            self.assertIn('data-act="play"', host)
            self.assertIn("resources/read", host)
            self.assertIn("tools/call", host)
            app = urlopen(
                url.rstrip("/") + "/app/recovery.html?story=recovery-run-few"
            ).read().decode("utf-8")
            self.assertIn('id="icon-file"', app)
            self.assertIn('id="boot"', app)
            self.assertNotIn("<!-- BEARING:ICONS -->", app)
            catalog = json.loads(urlopen(url.rstrip("/") + "/catalog.json").read().decode("utf-8"))
            self.assertIn("stories", catalog)
        finally:
            httpd.shutdown()
            httpd.server_close()


class CliListTest(BearingTestCase):
    def test_list_prints_story_ids_without_serving(self):
        result = run_cli(["ui-preview", "--list"])
        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout
        self.assertIn("recovery-run-few", stdout)
        self.assertIn("review-empty", stdout)
        self.assertNotIn("Ctrl-C", stdout)


if __name__ == "__main__":
    unittest.main()
