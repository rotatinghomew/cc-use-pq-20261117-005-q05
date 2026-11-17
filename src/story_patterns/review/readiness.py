from __future__ import annotations

from collections import defaultdict

from story_patterns.analysis.report import _consensus
from story_patterns.catalog.ordering import (
    event_locations,
    ordering_mode,
    ordering_review_summary,
    summarize_ordering,
)

# 队列顶层状态统计需要覆盖的次序状态。
QUEUE_ORDERING_STATES = (
    "legacy_continuous", "regular", "reordered", "source_gap", "duplicate_source",
)


def build_review_queue(stories: list[dict], decisions: dict, minimum: int, adjudications: dict | None = None) -> list[dict]:
    queue = []
    for story in sorted(stories, key=lambda item: (item["tradition"], item["story_id"], item["revision"])):
        identity = (story["story_id"], story["revision"])
        votes = decisions.get(identity, [])
        adjudication = (adjudications or {}).get(identity)
        pattern, pattern_status = _consensus([item["pattern"] for item in votes], minimum)
        outcome, outcome_status = _consensus([item["youngest_outcome"] for item in votes], minimum)
        cited = {event_id for vote in votes for event_id in vote["evidence_event_ids"]}
        missing_evidence = [event["event_id"] for event in story["events"] if event["event_id"] not in cited]
        if adjudication:
            status = "adjudicated"
        elif not votes:
            status = "unreviewed"
        elif pattern_status == "split" or outcome_status == "split":
            status = "disputed"
        elif pattern_status != "agreed" or outcome_status != "agreed":
            status = "needs_more_reviews"
        else:
            status = "ready"
        ordering = summarize_ordering(story["events"], ordering_mode(story))
        locations = event_locations(story["events"])
        queue.append({
            "story_id": story["story_id"], "revision": story["revision"], "title": story["title"],
            "tradition": story["tradition"], "status": status, "reviewer_count": len(votes),
            "pattern": pattern, "outcome": outcome, "missing_evidence_event_ids": missing_evidence,
            "reviewer_names": sorted(item["annotator"] for item in votes),
            "adjudication_id": adjudication["adjudication_id"] if adjudication else None,
            "final_pattern": adjudication["pattern"] if adjudication else pattern,
            "final_outcome": adjudication["youngest_outcome"] if adjudication else outcome,
            # 双轨次序状态：源位置、分析次序与跨章节范围各自可解释，
            # 缺段、重复引用与合法重排不会伪装成正常样本。
            "ordering": ordering_review_summary(ordering),
            "source_gaps": ordering["source_gaps"],
            "duplicate_source_references": ordering["duplicate_source_references"],
            "reordered_event_ids": ordering["reordered_event_ids"],
            "chapters": ordering["chapters"],
            "cross_chapter": ordering["cross_chapter"],
            "event_locations": locations,
        })
    return queue


def queue_totals(rows: list[dict]) -> dict:
    totals = defaultdict(int)
    for row in rows:
        totals[row["status"]] += 1
    return {key: totals.get(key, 0) for key in ("unreviewed", "needs_more_reviews", "disputed", "ready", "adjudicated")}


def queue_ordering_totals(rows: list[dict]) -> dict:
    """按可解释次序状态统计队列，并列出需要人工解释的修订。"""
    totals = defaultdict(int)
    flagged = defaultdict(list)
    for row in rows:
        state = row["ordering"]["ordering_state"]
        totals[state] += 1
        if state != "regular" and state != "legacy_continuous":
            flagged[state].append(f"{row['story_id']}@{row['revision']}")
    return {
        "by_ordering_state": {key: totals.get(key, 0) for key in QUEUE_ORDERING_STATES},
        "flagged_story_revisions": {key: sorted(flagged.get(key, [])) for key in QUEUE_ORDERING_STATES
                                    if flagged.get(key)},
        "cross_chapter_story_revisions": sorted(
            f"{row['story_id']}@{row['revision']}" for row in rows if row["cross_chapter"]
        ),
    }
