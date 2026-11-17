from __future__ import annotations

import json
import tempfile
from pathlib import Path

from story_patterns.application import StoryPatternApplication


def story(story_id="tale-a", revision=1, tradition="coast"):
    return {
        "story_id": story_id,
        "revision": revision,
        "title": f"Local tale {story_id}",
        "tradition": tradition,
        "source": {"reference": "Synthetic research card", "kind": "local_synthetic"},
        "characters": [
            {"character_id": "eldest", "name": "Elder", "sibling_order": 1},
            {"character_id": "middle", "name": "Middle", "sibling_order": 2},
            {"character_id": "youngest", "name": "Young", "sibling_order": 3},
        ],
        "events": [
            {"event_id": "first", "sequence": 1, "actor_id": "eldest", "action": "tries first", "consequence": "path closes", "evidence": "Synthetic event one"},
            {"event_id": "second", "sequence": 2, "actor_id": "middle", "action": "tries next", "consequence": "path narrows", "evidence": "Synthetic event two"},
            {"event_id": "third", "sequence": 3, "actor_id": "youngest", "action": "tries last", "consequence": "group reaches shelter", "evidence": "Synthetic event three"},
        ],
    }


def batch(stories=None, batch_id="batch-a"):
    return {"batch_id": batch_id, "stories": stories if stories is not None else [story()]}


def dual_order_story(story_id="tale-dual", revision=1, tradition="coast", events=None,
                     chapters=("ch-1", "ch-2")):
    """使用显式双轨字段（章节、源位置、分析次序）的故事，与旧式 sequence 区分。"""
    if events is None:
        # 默认：跨章节、源位置有缺段，分析次序与源位置自然顺序一致。
        events = [
            {"event_id": "e1", "chapter": chapters[0], "source_position": 1,
             "analysis_order": 1, "actor_id": "eldest", "action": "opens the road",
             "consequence": "path closes", "evidence": "Source ch-1 pos 1"},
            {"event_id": "e2", "chapter": chapters[0], "source_position": 3,
             "analysis_order": 2, "actor_id": "middle", "action": "tries again",
             "consequence": "path narrows", "evidence": "Source ch-1 pos 3 (pos 2 missing)"},
            {"event_id": "e3", "chapter": chapters[1], "source_position": 1,
             "analysis_order": 3, "actor_id": "youngest", "action": "reaches shelter",
             "consequence": "group is safe", "evidence": "Source ch-2 pos 1"},
        ]
    return {
        "story_id": story_id,
        "revision": revision,
        "title": f"Local dual-order tale {story_id}",
        "tradition": tradition,
        "source": {"reference": "Synthetic chapter excerpts", "kind": "local_synthetic"},
        "characters": [
            {"character_id": "eldest", "name": "Elder", "sibling_order": 1},
            {"character_id": "middle", "name": "Middle", "sibling_order": 2},
            {"character_id": "youngest", "name": "Young", "sibling_order": 3},
        ],
        "events": events,
    }


def decision(story_id="tale-a", revision=1, annotator="reader-a", sequence=1,
             pattern="parallel", outcome="wins", decision_id=None, evidence=None):
    return {
        "decision_id": decision_id or f"{story_id}-{annotator}-{sequence}",
        "story_id": story_id,
        "story_revision": revision,
        "annotator": annotator,
        "sequence": sequence,
        "pattern": pattern,
        "youngest_outcome": outcome,
        "evidence_event_ids": ["first", "third"] if evidence is None else evidence,
    }


class AppCase:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temporary.name) / "stories.sqlite3")
        self.app = StoryPatternApplication(self.database)

    def tearDown(self):
        self.temporary.cleanup()

    def import_story(self, record=None, batch_id="batch-a"):
        return self.app.import_batch(batch([record or story()], batch_id))

    def add_votes(self, story_id="tale-a", revision=1, values=None):
        votes = values or [
            decision(story_id, revision, "reader-a"),
            decision(story_id, revision, "reader-b"),
        ]
        return [self.app.record_decision(vote) for vote in votes]


def fixture(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
