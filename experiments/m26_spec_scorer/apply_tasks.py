"""M26 — apply hand-edited task list to the loom store.

`loom decompose --apply` regenerates from the SPEC; it doesn't support
applying a hand-edited YAML. This script reads proposed_tasks.yaml
(post-hand-edit) and creates each Task via the store API.

Run once. Verify with `loom task list -p loom --json`.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import yaml

from loom.embedding import get_embedding
from loom.store import LoomStore, Task, generate_impl_id


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    yaml_path = repo / "experiments" / "m26_spec_scorer" / "proposed_tasks.yaml"
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    store = LoomStore(
        project="loom",
        data_dir=Path.home() / ".openclaw" / "loom" / "loom",
    )

    # Build title → id map for dep wiring (depends_on_titles → depends_on)
    title_to_id: dict[str, str] = {}
    created: list[tuple[str, str]] = []
    now = datetime.datetime.now().isoformat()

    for entry in payload["tasks"]:
        title = entry["title"]
        depends_on = [
            title_to_id[t] for t in entry.get("depends_on_titles", [])
            if t in title_to_id
        ]
        missing = [
            t for t in entry.get("depends_on_titles", [])
            if t not in title_to_id
        ]
        if missing:
            print(f"⚠ unresolved deps for {title[:60]}...: {missing}", file=sys.stderr)

        task_id = generate_impl_id("TASK", title + now)
        task = Task(
            id=task_id,
            title=title,
            parent_spec=entry.get("parent_spec", ""),
            files_to_modify=entry.get("files_to_modify", []),
            test_to_write=entry.get("test_to_write", ""),
            context_reqs=entry.get("context_reqs", []),
            context_specs=entry.get("context_specs", []),
            context_patterns=entry.get("context_patterns", []),
            context_sidecars=entry.get("context_sidecars", []),
            context_files=entry.get("context_files", []),
            size_budget_files=entry.get("size_budget_files", 2),
            size_budget_loc=entry.get("size_budget_loc", 80),
            depends_on=depends_on,
            created_by="m26-pilot-handedit",
            timestamp=now,
        )

        embedding_text = f"{title}\n{task.parent_spec}"
        store.add_task(task, get_embedding(embedding_text))
        title_to_id[title] = task_id
        created.append((task_id, title[:80]))

    print(f"OK created {len(created)} task(s)")
    for tid, title in created:
        print(f"  {tid}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
