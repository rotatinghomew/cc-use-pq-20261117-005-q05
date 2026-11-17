from __future__ import annotations

from collections import defaultdict

from story_patterns.catalog.ordering import ordering_mode, summarize_ordering


def revision_lineage(stories: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for story in stories:
        grouped[story["story_id"]].append(story)
    result = []
    for story_id, versions in sorted(grouped.items()):
        versions.sort(key=lambda item: item["revision"])
        revision_numbers = [item["revision"] for item in versions]
        expected = list(range(1, revision_numbers[-1] + 1))
        missing = sorted(set(expected) - set(revision_numbers))
        titles_by_revision = []
        for item in versions:
            ordering = summarize_ordering(item["events"], ordering_mode(item))
            titles_by_revision.append({
                "revision": item["revision"],
                "title": item["title"],
                "ordering_mode": ordering["ordering_mode"],
                "ordering_state": ordering["ordering_state"],
                "chapter_count": ordering["chapter_count"],
                "cross_chapter": ordering["cross_chapter"],
                "source_gap_count": len(ordering["source_gaps"]),
                "duplicate_source_reference_count": len(ordering["duplicate_source_references"]),
            })
        result.append({
            "story_id": story_id,
            "revision_count": len(versions),
            "latest_revision": revision_numbers[-1],
            "missing_revision_numbers": missing,
            "titles_by_revision": titles_by_revision,
            "traditions": sorted({item["tradition"] for item in versions}),
        })
    return result


def lineage_warnings(lineage: list[dict]) -> list[dict]:
    return [{"story_id": item["story_id"], "missing_revision_numbers": item["missing_revision_numbers"]}
            for item in lineage if item["missing_revision_numbers"]]
