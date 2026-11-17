from __future__ import annotations

from story_patterns.catalog.ordering import event_locations, source_location


def evidence_coverage(stories: list[dict], decisions: dict) -> dict:
    total_events = 0
    cited_events = 0
    story_rows = []
    by_order = {}
    for story in stories:
        identity = (story["story_id"], story["revision"])
        votes = decisions.get(identity, [])
        cited = {event_id for vote in votes for event_id in vote["evidence_event_ids"]}
        known = {event["event_id"] for event in story["events"]}
        covered = known & cited
        total_events += len(known)
        cited_events += len(covered)
        character_order = {item["character_id"]: item["sibling_order"] for item in story["characters"]}
        locations = event_locations(story["events"])
        for event in story["events"]:
            order = character_order[event["actor_id"]]
            item = by_order.setdefault(order, {"events": 0, "cited_events": 0})
            item["events"] += 1
            item["cited_events"] += event["event_id"] in covered
        story_rows.append({
            "story_id": story["story_id"], "revision": story["revision"],
            "total_events": len(known), "cited_events": len(covered),
            "uncited_event_ids": sorted(known - covered),
            # 教师可凭源位置回到原文；分析次序另由 event_ordering 报告段表达。
            "event_source_locations": {
                event_id: locations[event_id]["source_location"] for event_id in sorted(known)
            },
            "uncited_source_locations": [
                source_location(event)
                for event in story["events"] if event["event_id"] not in covered
            ],
        })
    return {
        "total_events": total_events,
        "cited_events": cited_events,
        "coverage_rate": cited_events / total_events if total_events else None,
        "by_sibling_order": {
            str(order): {"events": values["events"], "cited_events": values["cited_events"],
                         "coverage_rate": values["cited_events"] / values["events"]}
            for order, values in sorted(by_order.items())
        },
        "stories": story_rows,
    }
