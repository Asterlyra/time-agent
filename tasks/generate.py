"""Persist reproducible public and private datasets separately."""
import json
from pathlib import Path
from tasks.data import generate


def main():
    root = Path(__file__).resolve().parent
    for split in ("dev", "test"):
        tasks = generate(split)
        for dirname, data in (
            (split, [{k: v for k, v in task.items() if k != "private"} for task in tasks]),
            ("private_answers", [{"task_id": task["task_id"], "private": task["private"]} for task in tasks]),
        ):
            dest = root / dirname
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{split}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
