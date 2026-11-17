from __future__ import annotations

from collections import defaultdict

from story_patterns.catalog.ordering import ordering_mode, ordering_review_summary, summarize_ordering
from story_patterns.catalog.validate import normalize_story
from story_patterns.errors import ValidationError


def preview_rows(rows: list[dict]) -> dict:
    """逐条汇总记录错误，同时保持正式批次导入的全有或全无语义。"""
    valid = []
    errors = []
    seen = defaultdict(list)
    ordering_notes = []
    for index, raw in enumerate(rows, start=1):
        try:
            story = normalize_story(raw)
        except ValidationError as error:
            errors.append({"row": index, "story_id": _candidate_id(raw), "error": str(error)})
            continue
        identity = (story["story_id"], story["revision"])
        seen[identity].append(index)
        valid.append((index, story))
    repeated_rows = {index for indexes in seen.values() if len(indexes) > 1 for index in indexes}
    for identity, indexes in seen.items():
        if len(indexes) > 1:
            for index in indexes:
                errors.append({"row": index, "story_id": identity[0],
                               "error": "story revision is repeated in this batch"})
    for index, story in valid:
        if index in repeated_rows:
            continue
        summary = summarize_ordering(story["events"], ordering_mode(story))
        note = {"row": index, "story_id": story["story_id"], "revision": story["revision"]}
        note.update(ordering_review_summary(summary))
        ordering_notes.append(note)
    valid = [(index, story) for index, story in valid if index not in repeated_rows]
    errors.sort(key=lambda item: (item["row"], item["error"]))
    return {"rows_seen": len(rows), "valid_rows": len(valid), "error_count": len(errors),
            "ready": bool(rows) and not errors, "errors": errors,
            "ordering_notes": ordering_notes,
            "normalized_stories": [story for _, story in valid]}


def _candidate_id(raw) -> str | None:
    if isinstance(raw, dict):
        value = raw.get("story_id")
        return value if isinstance(value, str) else None
    return None
