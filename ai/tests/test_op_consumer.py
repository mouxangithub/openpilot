"""Tests for OP consumer layer and CLI helpers."""

from __future__ import annotations

import unittest


class TestConsumerLexicon(unittest.TestCase):
  def test_param_label_known(self):
    from ai.common.consumer_lexicon import param_label
    self.assertEqual(param_label("FollowDistanceGap"), "跟车距离档位")

  def test_format_bool(self):
    from ai.common.consumer_lexicon import format_param_value
    self.assertEqual(format_param_value("Mads", True), "开启")

  def test_consumerize_diff(self):
    from ai.common.consumer_lexicon import consumerize_diff
    rows = consumerize_diff({
      "FollowDistanceGap": {"before": "1", "after": "3"},
    })
    self.assertEqual(len(rows), 1)
    self.assertEqual(rows[0]["label"], "跟车距离档位")

  def test_filter_consumer_language(self):
    from ai.common.consumer_lexicon import filter_consumer_language
    out = filter_consumer_language("Call write_params with confirm=true on dp_lon_accel")
    self.assertNotIn("write_params", out)
    self.assertIn("经您确认", out)


class TestConsumerWizards(unittest.TestCase):
  def test_list_wizards(self):
    from ai.tools.consumer_wizards import list_consumer_wizards
    w = list_consumer_wizards()
    self.assertGreaterEqual(len(w), 4)
    ids = {x["id"] for x in w}
    self.assertIn("tune_feel", ids)

  def test_resolve_slash(self):
    from ai.tools.consumer_wizards import resolve_wizard_by_slash
    hit = resolve_wizard_by_slash("/调手感")
    self.assertIsNotNone(hit)
    self.assertEqual(hit["id"], "tune_feel")


class TestConsumerTools(unittest.TestCase):
  def test_preview_without_params(self):
    from ai.tools.consumer_tools import preview_params_consumer
    out = preview_params_consumer({})
    self.assertFalse(out.get("ok"))

  def test_enrich_preview(self):
    from ai.tools.consumer_tools import enrich_write_preview
    out = enrich_write_preview({
      "FollowDistanceGap": {"before": "1", "after": "2"},
    })
    self.assertTrue(out.get("ok"))
    self.assertIn("consumer", out)


class TestOpCli(unittest.TestCase):
  def test_parser_has_commands(self):
    from ai.cli.main import build_parser
    parser = build_parser()
    with self.assertRaises(SystemExit):
      parser.parse_args([])
    args = parser.parse_args(["status"])
    self.assertEqual(args.command, "status")

  def test_parse_op_command(self):
    from ai.cli.runner import parse_op_command
    p = parse_op_command("op tune 跟车太远")
    self.assertIsNotNone(p)
    self.assertEqual(p["subcommand"], "tune")
    self.assertTrue(p["consumer_mode"])
    self.assertIsNone(parse_op_command("ls -la"))


  def test_wizard_aliases(self):
    from ai.cli.main import WIZARD_ALIASES
    self.assertEqual(WIZARD_ALIASES["doctor"], "cant_engage")


if __name__ == "__main__":
  unittest.main()
