import copy
import unittest

from story_patterns.analysis.event_ordering import build_event_ordering_section
from story_patterns.analysis.revision_drift import compare_revisions
from story_patterns.catalog.ordering import (
    ORDERING_MODE_EXPLICIT,
    ORDERING_MODE_LEGACY,
    STATE_DUPLICATE_SOURCE,
    STATE_REORDERED,
    STATE_SOURCE_GAP,
    event_locations,
    ordering_mode,
    source_location,
    summarize_ordering,
)
from story_patterns.catalog.validate import normalize_batch, normalize_story
from story_patterns.errors import ValidationError
from tests.support import AppCase, batch, dual_order_story, story


class DualOrderNormalizationTests(unittest.TestCase):
    def test_explicit_events_keep_source_position_and_analysis_order_distinct(self):
        normalized = normalize_story(dual_order_story())
        self.assertEqual(ordering_mode(normalized), ORDERING_MODE_EXPLICIT)
        first = normalized["events"][0]
        self.assertEqual(
            {key: first[key] for key in ("chapter", "source_position", "analysis_order")},
            {"chapter": "ch-1", "source_position": 1, "analysis_order": 1},
        )
        # 分析次序用于排序，而非源位置。
        self.assertEqual([event["analysis_order"] for event in normalized["events"]], [1, 2, 3])
        self.assertNotIn("sequence", first)

    def test_legacy_sequence_material_is_normalized_unchanged(self):
        normalized = normalize_story(story())
        self.assertEqual(ordering_mode(normalized), ORDERING_MODE_LEGACY)
        self.assertEqual([event["sequence"] for event in normalized["events"]], [1, 2, 3])
        self.assertTrue(all("chapter" not in event for event in normalized["events"]))

    def test_mixing_sequence_and_dual_fields_is_rejected(self):
        raw = dual_order_story()
        raw["events"][0]["sequence"] = 1
        with self.assertRaisesRegex(ValidationError, "one ordering scheme"):
            normalize_story(raw)

    def test_analysis_order_must_be_unique_and_contiguous(self):
        duplicate = dual_order_story()
        duplicate["events"][1]["analysis_order"] = 1
        with self.assertRaisesRegex(ValidationError, "analysis_order values must be unique"):
            normalize_story(duplicate)
        gap = dual_order_story()
        gap["events"][2]["analysis_order"] = 4
        with self.assertRaisesRegex(ValidationError, "analysis_order values must be contiguous"):
            normalize_story(gap)

    def test_source_position_gap_and_duplicate_are_accepted_but_flagged(self):
        raw = dual_order_story()
        # 制造重复引用：两个事件指向 ch-1 的同一原文位置。
        raw["events"][1]["source_position"] = 1
        normalized = normalize_story(raw)
        summary = summarize_ordering(normalized["events"], ORDERING_MODE_EXPLICIT)
        self.assertEqual(summary["ordering_state"], STATE_DUPLICATE_SOURCE)
        self.assertEqual(summary["duplicate_source_references"][0]["event_ids"], ["e1", "e2"])

    def test_legitimate_reorder_is_distinguished_from_source_gap(self):
        raw = dual_order_story()
        # 源位置连续，但分析次序把最后的原文事件提到最前。
        raw["events"][0]["source_position"] = 1
        raw["events"][1]["source_position"] = 2
        raw["events"][2]["source_position"] = 3
        raw["events"][0]["analysis_order"] = 2
        raw["events"][1]["analysis_order"] = 3
        raw["events"][2]["analysis_order"] = 1
        normalized = normalize_story(raw)
        summary = summarize_ordering(normalized["events"], ORDERING_MODE_EXPLICIT)
        self.assertEqual(summary["ordering_state"], STATE_REORDERED)
        self.assertEqual(summary["reordered_event_ids"], ["e1", "e2", "e3"])
        self.assertEqual(summary["source_gaps"], [])

    def test_gap_state_reports_chapter_and_missing_position(self):
        normalized = normalize_story(dual_order_story())
        summary = summarize_ordering(normalized["events"], ORDERING_MODE_EXPLICIT)
        self.assertEqual(summary["ordering_state"], STATE_SOURCE_GAP)
        self.assertEqual(summary["source_gaps"], [{"chapter": "ch-1", "missing_source_position": 2}])
        self.assertTrue(summary["cross_chapter"])
        self.assertEqual(summary["chapters"], ["ch-1", "ch-2"])

    def test_positive_integer_and_text_rules_apply_to_dual_fields(self):
        for field, value in [("source_position", 0), ("source_position", "2"),
                             ("analysis_order", True), ("chapter", " ")]:
            with self.subTest(field=field):
                raw = dual_order_story()
                raw["events"][0][field] = value
                with self.assertRaises(ValidationError):
                    normalize_story(raw)

    def test_normalization_does_not_mutate_callers_document(self):
        raw = dual_order_story()
        before = copy.deepcopy(raw)
        normalize_story(raw)
        self.assertEqual(raw, before)

    def test_event_locations_resolve_both_orders(self):
        normalized = normalize_story(dual_order_story())
        locations = event_locations(normalized["events"])
        self.assertEqual(locations["e2"]["source_location"], {"chapter": "ch-1", "source_position": 3})
        self.assertEqual(locations["e2"]["analysis_order"], 2)
        legacy = normalize_story(story())
        self.assertEqual(source_location(legacy["events"][0]), {"chapter": None, "source_position": 1})


class OrderingQueueAndReportTests(AppCase, unittest.TestCase):
    def test_queue_keeps_gap_duplicate_and_reorder_states_interpretable(self):
        gapped = dual_order_story("gapped")
        duplicate = dual_order_story("duplicated")
        duplicate["events"][1]["source_position"] = 1
        reordered = dual_order_story("reordered")
        for event in reordered["events"]:
            event["source_position"] = event["analysis_order"]
        reordered["events"][0]["analysis_order"] = 3
        reordered["events"][2]["analysis_order"] = 1
        self.app.import_batch(batch([gapped, duplicate, reordered], "dual-batch"))
        queue = self.app.review_queue()
        states = {row["story_id"]: row["ordering"]["ordering_state"] for row in queue["stories"]}
        self.assertEqual(states["gapped"], STATE_SOURCE_GAP)
        self.assertEqual(states["duplicated"], STATE_DUPLICATE_SOURCE)
        self.assertEqual(states["reordered"], STATE_REORDERED)
        totals = queue["ordering"]["by_ordering_state"]
        self.assertEqual(totals["source_gap"], 1)
        self.assertEqual(totals["duplicate_source"], 1)
        self.assertEqual(totals["reordered"], 1)
        flagged = queue["ordering"]["flagged_story_revisions"]
        self.assertIn("gapped@1", flagged["source_gap"])
        # 所有双轨样本都跨章节。
        self.assertEqual(
            queue["ordering"]["cross_chapter_story_revisions"],
            ["duplicated@1", "gapped@1", "reordered@1"],
        )

    def test_queue_row_carries_source_locations_for_each_event(self):
        self.app.import_batch(batch([dual_order_story()], "one"))
        row = self.app.review_queue()["stories"][0]
        self.assertEqual(row["event_locations"]["e1"]["source_location"],
                         {"chapter": "ch-1", "source_position": 1})
        self.assertEqual(row["source_gaps"], [{"chapter": "ch-1", "missing_source_position": 2}])

    def test_report_event_ordering_section_and_story_results(self):
        self.app.import_batch(batch([dual_order_story(), story("legacy-one")], "mixed"))
        report = self.app.create_report()
        section = report["event_ordering"]
        self.assertEqual(section["mode_counts"],
                         {ORDERING_MODE_LEGACY: 1, ORDERING_MODE_EXPLICIT: 1})
        self.assertEqual(section["state_counts"]["source_gap"], 1)
        self.assertEqual(section["state_counts"]["legacy_continuous"], 1)
        self.assertEqual(section["cross_chapter_story_revisions"], ["tale-dual@1"])
        by_id = {row["story_id"]: row for row in report["story_results"]}
        self.assertEqual(by_id["tale-dual"]["ordering_state"], STATE_SOURCE_GAP)
        self.assertTrue(by_id["tale-dual"]["cross_chapter"])
        self.assertEqual(by_id["legacy-one"]["ordering_state"], "legacy_continuous")
        self.assertIn("evidence_binding", report["provenance"])

    def test_evidence_coverage_reports_source_locations_of_uncited_events(self):
        self.app.import_batch(batch([dual_order_story()], "one"))
        self.app.record_decision({
            "decision_id": "d1", "story_id": "tale-dual", "story_revision": 1,
            "annotator": "reader-a", "sequence": 1, "pattern": "parallel",
            "youngest_outcome": "wins", "evidence_event_ids": ["e1"],
        })
        report = self.app.create_report()
        coverage = report["evidence_coverage"]["stories"][0]
        self.assertEqual(coverage["uncited_source_locations"],
                         [{"chapter": "ch-1", "source_position": 3},
                          {"chapter": "ch-2", "source_position": 1}])

    def test_history_binds_decisions_to_their_revision_source_locations(self):
        self.app.import_batch(batch([dual_order_story()], "one"))
        self.app.record_decision({
            "decision_id": "d1", "story_id": "tale-dual", "story_revision": 1,
            "annotator": "reader-a", "sequence": 1, "pattern": "parallel",
            "youngest_outcome": "wins", "evidence_event_ids": ["e1", "e3"],
        })
        history = self.app.review_history("tale-dual", 1)
        self.assertEqual(history["decisions"][0]["evidence_locations"]["e3"]["source_location"],
                         {"chapter": "ch-2", "source_position": 1})
        self.assertEqual(history["ordering"]["ordering_state"], STATE_SOURCE_GAP)


class CrossRevisionBindingTests(AppCase, unittest.TestCase):
    def _two_revisions_with_moved_event(self):
        first = dual_order_story(revision=1)
        second = dual_order_story(revision=2)
        # 沿用 event_id，但在新版移动源位置与分析次序。
        second["events"][0]["source_position"] = 2
        second["events"][0]["analysis_order"] = 2
        second["events"][1]["analysis_order"] = 1
        return first, second

    def test_revision_drift_separates_source_moves_from_analysis_reorders(self):
        first, second = self._two_revisions_with_moved_event()
        changes = compare_revisions([first, second])
        change = changes[0]
        self.assertIn("e1", change["event_source_locations_changed"])
        self.assertIn("e1", change["event_analysis_orders_changed"])
        self.assertFalse(change["prior_decisions_carry_over"])
        self.assertIn("never re-points", change["decision_binding_note"])

    def test_old_decision_does_not_apply_to_new_revision_events(self):
        first, second = self._two_revisions_with_moved_event()
        self.app.import_batch(batch([first], "rev1"))
        self.app.import_batch(batch([second], "rev2"))
        self.app.record_decision({
            "decision_id": "old-vote", "story_id": "tale-dual", "story_revision": 1,
            "annotator": "reader-a", "sequence": 1, "pattern": "harm",
            "youngest_outcome": "wins", "evidence_event_ids": ["e1"],
        })
        report = self.app.create_report()
        rows = {(row["story_id"], row["revision"]): row for row in report["story_results"]}
        # 新版没有任何判断，旧判断不自动指向新版。
        self.assertEqual(rows[("tale-dual", 2)]["reviewer_count"], 0)
        self.assertEqual(rows[("tale-dual", 2)]["pattern_status"], "insufficient")
        self.assertEqual(rows[("tale-dual", 1)]["pattern_status"], "insufficient")

    def test_duplicate_source_revision_can_still_collect_evidence_backed_decisions(self):
        raw = dual_order_story()
        raw["events"][1]["source_position"] = 1  # 重复引用
        self.app.import_batch(batch([raw], "dup"))
        decision = {
            "decision_id": "d1", "story_id": "tale-dual", "story_revision": 1,
            "annotator": "reader-a", "sequence": 1, "pattern": "parallel",
            "youngest_outcome": "wins", "evidence_event_ids": ["e1", "e2"],
        }
        self.app.record_decision(decision)
        report = self.app.create_report()
        section = next(row for row in report["event_ordering"]["stories"]
                       if row["story_id"] == "tale-dual")
        self.assertEqual(section["cited_event_ids_on_duplicate_source"], ["e1", "e2"])
        # 单条判断内仍不允许重复引用同一事件。
        decision["decision_id"] = "d2"
        decision["evidence_event_ids"] = ["e1", "e1"]
        with self.assertRaises(ValidationError):
            self.app.record_decision(decision)


class ManifestLineageAndSearchTests(AppCase, unittest.TestCase):
    def test_manifest_and_lineage_expose_chapter_scope_and_state(self):
        self.app.import_batch(batch([dual_order_story(), story("legacy")], "batch"))
        manifest = self.app.catalog_manifest()
        dual = next(row for row in manifest["story_revisions"] if row["story_id"] == "tale-dual")
        self.assertTrue(dual["cross_chapter"])
        self.assertEqual(dual["chapters"], ["ch-1", "ch-2"])
        self.assertEqual(dual["ordering_state"], STATE_SOURCE_GAP)
        lineage = self.app.revision_lineage()
        entry = next(row for row in lineage if row["story_id"] == "tale-dual")
        self.assertEqual(entry["titles_by_revision"][0]["chapter_count"], 2)

    def test_search_filters_by_chapter_and_returns_source_locations(self):
        self.app.import_batch(batch([dual_order_story()], "batch"))
        result = self.app.search_stories(chapter="ch-2")
        self.assertEqual([row["story_id"] for row in result], ["tale-dual"])
        self.assertEqual(result[0]["event_source_locations"]["e3"]["chapter"], "ch-2")
        self.assertEqual(self.app.search_stories(chapter="ch-9"), [])
        with self.assertRaises(ValidationError):
            self.app.search_stories(chapter=" ")

    def test_preview_summarizes_ordering_state_without_writing(self):
        result = self.app.catalog.preview([dual_order_story(), story()])
        states = {note["story_id"]: note["ordering_state"] for note in result["ordering_notes"]}
        self.assertEqual(states["tale-dual"], STATE_SOURCE_GAP)
        self.assertEqual(states["tale-a"], "legacy_continuous")
        self.assertEqual(self.app.catalog.list_stories(), [])

    def test_batch_digest_changes_when_analysis_order_changes(self):
        raw = dual_order_story()
        first_batch = normalize_batch(batch([copy.deepcopy(raw)], "b1"))
        raw["events"][0]["analysis_order"], raw["events"][2]["analysis_order"] = 3, 1
        # 重排后分析次序不再连续，需重排为合法连续值。
        raw["events"][1]["analysis_order"] = 2
        second_batch = normalize_batch(batch([raw], "b2"))
        self.assertNotEqual(first_batch[2], second_batch[2])


if __name__ == "__main__":
    unittest.main()
