from __future__ import annotations

from collections import defaultdict

from story_patterns.catalog.ordering import ordering_rank, source_location


def _location_key(event: dict) -> tuple:
    location = source_location(event)
    return location["chapter"], location["source_position"]


def compare_revisions(stories: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for story in stories:
        grouped[story["story_id"]].append(story)
    changes = []
    for story_id, versions in sorted(grouped.items()):
        versions.sort(key=lambda item: item["revision"])
        for previous, current in zip(versions, versions[1:]):
            previous_characters = {item["character_id"]: item for item in previous["characters"]}
            current_characters = {item["character_id"]: item for item in current["characters"]}
            previous_events = {item["event_id"]: item for item in previous["events"]}
            current_events = {item["event_id"]: item for item in current["events"]}
            shared_events = previous_events.keys() & current_events.keys()
            # 同一 event_id 在新版中的源位置移动（引用原文位置变化）。
            source_location_changed = sorted(
                event_id for event_id in shared_events
                if _location_key(previous_events[event_id]) != _location_key(current_events[event_id])
            )
            # 源位置不变但分析次序变化：研究者对相同原文材料做了合法重排。
            analysis_order_changed = sorted(
                event_id for event_id in shared_events
                if ordering_rank(previous_events[event_id]) != ordering_rank(current_events[event_id])
            )
            previous_chapters = {source_location(event)["chapter"] for event in previous["events"]}
            current_chapters = {source_location(event)["chapter"] for event in current["events"]}
            changes.append({
                "story_id": story_id,
                "from_revision": previous["revision"], "to_revision": current["revision"],
                "title_changed": previous["title"] != current["title"],
                "tradition_changed": previous["tradition"] != current["tradition"],
                "source_changed": previous["source"] != current["source"],
                "characters_added": sorted(current_characters.keys() - previous_characters.keys()),
                "characters_removed": sorted(previous_characters.keys() - current_characters.keys()),
                "sibling_orders_changed": sorted(
                    key for key in previous_characters.keys() & current_characters.keys()
                    if previous_characters[key]["sibling_order"] != current_characters[key]["sibling_order"]
                ),
                "events_added": sorted(current_events.keys() - previous_events.keys()),
                "events_removed": sorted(previous_events.keys() - current_events.keys()),
                "event_content_changed": sorted(
                    event_id for event_id in shared_events
                    if previous_events[event_id] != current_events[event_id]
                ),
                "event_source_locations_changed": source_location_changed,
                "event_analysis_orders_changed": analysis_order_changed,
                "chapter_scope_changed": previous_chapters != current_chapters,
                # 即使 event_id 被沿用，旧版判断也不自动指向新版事件；每个修订独立标注。
                "requires_separate_review": True,
                "prior_decisions_carry_over": False,
                "decision_binding_note": (
                    "reader and moderator decisions stay bound to the source locations of their own "
                    "revision; reusing an event id never re-points an older judgment"
                ),
            })
    return changes
