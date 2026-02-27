import json
import os
from typing import List, Tuple, Dict, Any

from domain import Task, Tag, Settings, now_ts


class JsonRepository:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Tuple[List[Task], Settings, List[Tag]]:
        if not os.path.exists(self.path):
            tasks = [Task(id="", text="任务样式", tag="默认", done=False)]
            settings = Settings()
            # 首次生成 storage.json：默认关闭同步（避免未配置时产生定时拉取/覆盖）
            tags = [Tag(id="", name="全部"), Tag(id="", name="默认")]
            self.save(tasks, settings, tags)
            return tasks, settings, tags

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw: Dict[str, Any] = json.load(f)

            settings = Settings.from_dict(raw.get("settings", {}))

            tags_raw = raw.get("tags", [])
            tags: List[Tag] = []
            tag_colors = raw.get("tag_colors", {}) if isinstance(raw, dict) else {}
            if isinstance(tags_raw, list) and tags_raw and isinstance(tags_raw[0], dict):
                tags = [Tag.from_dict(x) for x in tags_raw]
            else:
                names = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
                if not names:
                    names = ["默认"]
                if "默认" not in names:
                    names.append("默认")
                if "全部" not in names:
                    names.insert(0, "全部")
                for n in names:
                    c = ""
                    if isinstance(tag_colors, dict):
                        c = str(tag_colors.get(n, "") or "")
                    tags.append(Tag(id="", name=n, color=c))

            seen=set(); norm=[]
            for t in tags:
                t.name=(t.name or "").strip() or "默认"
                if t.name in seen: 
                    continue
                seen.add(t.name); norm.append(t)
            tags=norm
            if not any(t.name=="全部" for t in tags):
                tags.insert(0, Tag(id="", name="全部"))
            if not any(t.name=="默认" for t in tags):
                tags.append(Tag(id="", name="默认"))

            tasks_raw = raw.get("tasks", []) if isinstance(raw, dict) else []
            tasks = [Task.from_dict(x) for x in tasks_raw] if isinstance(tasks_raw, list) else []
            if not tasks:
                tasks = [Task(id="", text="任务样式", tag="默认", done=False)]

            # inject order if missing (respect current list order)
            max_order = max([t.order for t in tasks] + [now_ts()])
            step = 0.001
            for i, t in enumerate(tasks):
                if not t.order:
                    t.order = max_order - i*step

            tag_names = {t.name for t in tags if not t.deleted}
            for task in tasks:
                if task.tag not in tag_names:
                    tags.append(Tag(id="", name=task.tag))
                    tag_names.add(task.tag)

            return tasks, settings, tags
        except Exception:
            tasks = [Task(id="", text="任务样式", tag="默认", done=False)]
            settings = Settings()
            tags = [Tag(id="", name="全部"), Tag(id="", name="默认")]
            self.save(tasks, settings, tags)
            return tasks, settings, tags

    def save(self, tasks: List[Task], settings: Settings, tags: List[Tag]) -> None:
        payload = {
            "version": 8,
            "settings": settings.to_dict(),
            "tags": [t.to_dict() for t in tags],
            "tasks": [t.to_dict() for t in tasks],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)