from __future__ import annotations

from story_patterns.catalog.ordering import ordering_mode, summarize_ordering


def build_manifest(batches: list[dict], stories: list[dict]) -> dict:
    by_tradition = {}
    for story in stories:
        by_tradition[story["tradition"]] = by_tradition.get(story["tradition"], 0) + 1
    return {
        "batch_count": len(batches),
        "story_revision_count": len(stories),
        "tradition_counts": dict(sorted(by_tradition.items())),
        "batches": sorted(batches, key=lambda item: item["batch_id"]),
        "story_revisions": [
            _story_revision(story)
            for story in sorted(stories, key=lambda value: (value["story_id"], value["revision"]))
        ],
    }


def _story_revision(story: dict) -> dict:
    ordering = summarize_ordering(story["events"], ordering_mode(story))
    return {
        "story_id": story["story_id"], "revision": story["revision"],
        "source_reference": story["source"]["reference"], "source_kind": story["source"]["kind"],
        "ordering_mode": ordering["ordering_mode"],
        "ordering_state": ordering["ordering_state"],
        "cross_chapter": ordering["cross_chapter"],
        "chapters": ordering["chapters"],
        "chapter_count": ordering["chapter_count"],
        "source_gap_count": len(ordering["source_gaps"]),
        "duplicate_source_reference_count": len(ordering["duplicate_source_references"]),
    }
