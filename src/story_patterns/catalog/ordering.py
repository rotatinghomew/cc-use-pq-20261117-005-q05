"""事件次序的双轨模型。

同一条事件在语料里有两种彼此独立的次序，必须分开表达：

* 源位置（``chapter`` + ``source_position``）：原文中的位置，供教师引用原文；
  章节摘录可能缺段，也可能有两条记录指向同一原文位置（重复引用）。
* 分析次序（``analysis_order``）：研究者用于分析的先后顺序，允许与原文位置
  合法重排；在一个故事修订内部必须连续、唯一。

只提供旧式 ``sequence`` 字段的连续事件材料仍按原方式处理：其 ``sequence``
同时充当源位置与分析次序，章节范围为单章，状态保持 ``legacy_continuous``。
"""

from __future__ import annotations

from collections import defaultdict

LEGACY_CHAPTER = "__single_chapter__"

ORDERING_MODE_LEGACY = "legacy_continuous"
ORDERING_MODE_EXPLICIT = "explicit_dual_order"

STATE_LEGACY = "legacy_continuous"
STATE_REGULAR = "regular"
STATE_REORDERED = "reordered"
STATE_SOURCE_GAP = "source_gap"
STATE_DUPLICATE_SOURCE = "duplicate_source"

# 异常状态的优先级：重复引用与缺段需要先解释，重排其次。
STATE_PRECEDENCE = (
    STATE_DUPLICATE_SOURCE,
    STATE_SOURCE_GAP,
    STATE_REORDERED,
    STATE_REGULAR,
    STATE_LEGACY,
)


def event_ordering_mode(raw_events: list[dict]) -> str | None:
    """判断一批原始事件使用双轨字段还是旧式连续 sequence。"""
    explicit = [item for item in raw_events if isinstance(item, dict)
                and ("analysis_order" in item or "source_position" in item or "chapter" in item)]
    legacy = [item for item in raw_events if isinstance(item, dict) and "sequence" in item]
    if explicit and legacy:
        return "mixed"
    if explicit:
        return ORDERING_MODE_EXPLICIT
    if legacy:
        return ORDERING_MODE_LEGACY
    return None


def ordering_mode(story: dict) -> str:
    """规范化故事文档的次序模式。"""
    events = story.get("events", [])
    if events and "sequence" in events[0]:
        return ORDERING_MODE_LEGACY
    return ORDERING_MODE_EXPLICIT


def source_location(event: dict) -> dict:
    """把规范化事件解析为可引用的源位置。"""
    if "sequence" in event:
        return {"chapter": None, "source_position": event["sequence"]}
    return {"chapter": event.get("chapter"), "source_position": event["source_position"]}


def ordering_rank(event: dict) -> int:
    """分析次序：双轨事件用 analysis_order，旧式事件用 sequence。"""
    return event.get("analysis_order", event.get("sequence"))


def event_locations(events: list[dict]) -> dict:
    return {
        event["event_id"]: {
            "source_location": source_location(event),
            "analysis_order": ordering_rank(event),
        }
        for event in events
    }


def summarize_ordering(events: list[dict], mode: str) -> dict:
    """计算一个故事修订的可解释次序状态。

    缺段与重复引用不会在此抛错——它们以显式状态保留在结果中，供审阅队列与
    报告解释；硬性结构约束由导入校验负责。
    """
    if mode == ORDERING_MODE_LEGACY:
        positions = [event["sequence"] for event in events]
        return {
            "ordering_mode": ORDERING_MODE_LEGACY,
            "ordering_state": STATE_LEGACY,
            "chapters": [LEGACY_CHAPTER],
            "chapter_count": 1,
            "cross_chapter": False,
            "analysis_orders": sorted(positions),
            "reordered_event_ids": [],
            "source_gaps": [],
            "duplicate_source_references": [],
            "chapter_ranges": {LEGACY_CHAPTER: {"first": min(positions), "last": max(positions)}},
        }

    analysis_orders = sorted(event["analysis_order"] for event in events)
    chapters = sorted({event["chapter"] for event in events})
    by_chapter: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_chapter[event["chapter"]].append(event)

    gaps = []
    chapter_ranges = {}
    location_to_events: dict[tuple[str, int], list[str]] = defaultdict(list)
    for chapter in chapters:
        chapter_events = by_chapter[chapter]
        positions = sorted(event["source_position"] for event in chapter_events)
        chapter_ranges[chapter] = {"first": positions[0], "last": positions[-1]}
        present = set(positions)
        for position in range(positions[0], positions[-1] + 1):
            if position not in present:
                gaps.append({"chapter": chapter, "missing_source_position": position})
        for event in chapter_events:
            location_to_events[(chapter, event["source_position"])].append(event["event_id"])

    duplicates = [
        {"chapter": chapter, "source_position": position, "event_ids": sorted(event_ids)}
        for (chapter, position), event_ids in sorted(location_to_events.items())
        if len(event_ids) > 1
    ]

    # 合法重排：源位置的自然先后与分析次序不一致。重复引用时该比较不可靠，
    # 因此只在无重复引用时给出重排结论。
    reordered = []
    if not duplicates:
        source_ranked = sorted(events, key=lambda event: (event["chapter"], event["source_position"]))
        for source_index, event in enumerate(source_ranked, start=1):
            if event["analysis_order"] != source_index:
                reordered.append(event["event_id"])
    reordered.sort()

    state = _state(duplicates, gaps, reordered)
    return {
        "ordering_mode": ORDERING_MODE_EXPLICIT,
        "ordering_state": state,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "cross_chapter": len(chapters) > 1,
        "analysis_orders": analysis_orders,
        "reordered_event_ids": reordered,
        "source_gaps": gaps,
        "duplicate_source_references": duplicates,
        "chapter_ranges": chapter_ranges,
    }


def _state(duplicates: list[dict], gaps: list[dict], reordered: list[str]) -> str:
    if duplicates:
        return STATE_DUPLICATE_SOURCE
    if gaps:
        return STATE_SOURCE_GAP
    if reordered:
        return STATE_REORDERED
    return STATE_REGULAR


def ordering_review_summary(summary: dict) -> dict:
    """审阅队列用的精简视图，保留全部可解释字段。"""
    return {
        "ordering_mode": summary["ordering_mode"],
        "ordering_state": summary["ordering_state"],
        "cross_chapter": summary["cross_chapter"],
        "chapter_count": summary["chapter_count"],
        "chapters": summary["chapters"],
        "source_gap_count": len(summary["source_gaps"]),
        "duplicate_source_reference_count": len(summary["duplicate_source_references"]),
        "reordered_event_count": len(summary["reordered_event_ids"]),
    }
