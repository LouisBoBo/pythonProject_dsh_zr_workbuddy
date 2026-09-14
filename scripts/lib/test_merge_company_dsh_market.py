#!/usr/bin/env python3
"""merge_company_dsh_market 纯函数单测（不访问网络）。"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_company_dsh_market import (  # noqa: E402
    catalog_usable,
    merge_catalogs,
    plugin_identity,
    should_refresh_official,
    OFFICIAL_TTL_S,
    OFFICIAL_FAIL_BACKOFF_S,
)


def _plug(name: str, **extra):
    row = {
        "name": name,
        "owner": "中软",
        "url": f"https://example.test/{name}",
        "category": "tools",
        "description": {"zh": name, "en": name},
        "npm": name,
        "install": f"dsh plugin add {name}",
        "added": "2026-09-11",
    }
    row.update(extra)
    return row


class MergeCatalogsTest(unittest.TestCase):
    def test_company_plugins_first_and_deduped(self):
        company = {
            "name": "company-dsh-plugins",
            "categories": {"tools": {"zh": "工具与能力", "en": "Tools"}},
            "plugins": [_plug("@zhongruan/a"), _plug("@zhongruan/b")],
        }
        official = {
            "categories": {
                "tools": {"zh": "工具", "en": "Tools"},
                "theme": {"zh": "主题", "en": "Themes"},
            },
            "plugins": [
                _plug("popular", downloads=9000, stars=100),
                _plug("@zhongruan/a", downloads=1),  # 不得盖住公司同名包
                _plug("other", downloads=10, stars=2),
            ],
        }
        merged = merge_catalogs(company, official)
        names = [p["name"] for p in merged["plugins"]]
        self.assertEqual(names[:2], ["@zhongruan/a", "@zhongruan/b"])
        self.assertIn("popular", names)
        self.assertIn("other", names)
        self.assertEqual(names.count("@zhongruan/a"), 1)
        self.assertGreater(merged["plugins"][0]["downloads"], 9000)
        self.assertGreater(merged["plugins"][0]["downloads"], merged["plugins"][1]["downloads"])
        self.assertIn("zhongruan", merged["plugins"][0]["category"])
        self.assertEqual(merged["workbuddy_merge"]["company_count"], 2)
        self.assertEqual(merged["workbuddy_merge"]["official_count"], 2)
        self.assertIn("zhongruan", merged["categories"])
        self.assertIn("theme", merged["categories"])

    def test_official_missing_still_has_company(self):
        company = {"plugins": [_plug("@zhongruan/a"), _plug("@zhongruan/b")]}
        merged = merge_catalogs(company, None)
        self.assertEqual(len(merged["plugins"]), 2)
        self.assertEqual(merged["plugins"][0]["name"], "@zhongruan/a")
        self.assertEqual(merged["workbuddy_merge"]["official_count"], 0)

    def test_empty_official_dict_ignored(self):
        company = {"plugins": [_plug("@zhongruan/a")]}
        merged = merge_catalogs(company, {"plugins": []})
        self.assertEqual([p["name"] for p in merged["plugins"]], ["@zhongruan/a"])

    def test_catalog_usable(self):
        self.assertFalse(catalog_usable(None))
        self.assertFalse(catalog_usable({"plugins": []}))
        self.assertTrue(catalog_usable({"plugins": [_plug("x")]}))

    def test_plugin_identity_prefers_npm(self):
        self.assertEqual(plugin_identity({"name": "A", "npm": "@scope/a"}), "@scope/a")
        self.assertEqual(plugin_identity({"name": "A"}), "a")


class TtlTest(unittest.TestCase):
    def test_skip_within_success_ttl(self):
        now = 2_000_000
        meta = {"official_ok_at": now - 3600, "official_last_attempt_at": now - 3600}
        self.assertFalse(should_refresh_official(meta, now))

    def test_refresh_after_one_day(self):
        now = 2_000_000
        meta = {
            "official_ok_at": now - OFFICIAL_TTL_S - 1,
            "official_last_attempt_at": now - OFFICIAL_TTL_S - 1,
        }
        self.assertTrue(should_refresh_official(meta, now))

    def test_backoff_after_failure(self):
        now = 2_000_000
        meta = {
            "official_ok_at": 0,
            "official_last_attempt_at": now - OFFICIAL_FAIL_BACKOFF_S + 10,
        }
        self.assertFalse(should_refresh_official(meta, now))


if __name__ == "__main__":
    unittest.main()
