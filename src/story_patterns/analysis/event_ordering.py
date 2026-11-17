"""分析侧的事件次序汇总。

把每条故事修订的源位置、分析次序与跨章节范围汇总到报告中，并核对判断引用的
事件位置。判断只通过本修订的 event_id 绑定，缺段、重复引用与合法重排都以
显式状态保留，不会让旧判断自动指向新版事件。
"""

from __future__ import annotations

from collections import Counter

from story_patterns.catalog.ordering import (
    event_locations,
    ordering_mode,
    ordering_review_summary,
    summarize_ordering,
)


def build_event_ordering_section(stories: list[dict], decisions: dict) -> dict:
    state_counts: Counter = Counter()
    mode_counts: Counter = Counter()
    total_gaps = 0
    total_duplicates = 0
    total_reordered = 0
    cross_chapter_revisions = []
    story_rows = []
    for story in stories:
        identity = (story["story_id"], story["revision"])
        mode = ordering_mode(story)
        summary = summarize_ordering(story["events"], mode)
        review = ordering_review_summary(summary)
        mode_counts[mode] += 1
        state_counts[summary["ordering_state"]] += 1
        total_gaps += len(summary["source_gaps"])
        total_duplicates += len(summary["duplicate_source_references"])
        total_reordered += len(summary["reordered_event_ids"])
        if summary["cross_chapter"]:
            cross_chapter_revisions.append(f"{identity[0]}@{identity[1]}")
        votes = decisions.get(identity, [])
        cited = {event_id for vote in votes for event_id in vote["evidence_event_ids"]}
        # 被引用事件落在重复源位置或缺段附近时，审阅者应能直接看到解释状态。
        cited_on_duplicate = sorted(
            event_id
            for duplicate in summary["duplicate_source_references"]
            for event_id in duplicate["event_ids"]
            if event_id in cited
        )
        story_rows.append({
            "story_id": identity[0], "revision": identity[1],
            "ordering_mode": review["ordering_mode"],
            "ordering_state": review["ordering_state"],
            "chapters": review["chapters"],
            "chapter_count": review["chapter_count"],
            "cross_chapter": review["cross_chapter"],
            "source_gaps": summary["source_gaps"],
            "duplicate_source_references": summary["duplicate_source_references"],
            "reordered_event_ids": summary["reordered_event_ids"],
            "cited_event_ids_on_duplicate_source": cited_on_duplicate,
            "event_locations": event_locations(story["events"]),
        })
    return {
        "ordering_axes": {
            "source_location": "chapter plus source_position, used to cite the original text",
            "analysis_order": "contiguous per-revision order used for analysis; may legitimately reorder source",
            "cross_chapter_scope": "a revision spans more than one source chapter",
        },
        "mode_counts": dict(sorted(mode_counts.items())),
        "state_counts": {
            key: state_counts.get(key, 0)
            for key in ("legacy_continuous", "regular", "reordered", "source_gap", "duplicate_source")
        },
        "source_gap_count": total_gaps,
        "duplicate_source_reference_count": total_duplicates,
        "reordered_event_count": total_reordered,
        "cross_chapter_story_revisions": sorted(cross_chapter_revisions),
        "interpretation_limit": (
            "Ordering states describe source layout only; they are not literary conclusions. "
            "Reader decisions stay bound to their own revision's event ids."
        ),
        "stories": story_rows,
    }
