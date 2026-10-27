from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    corpus = json.loads((DATA_DIR / "reference_corpus.json").read_text(encoding="utf-8"))
    records = []
    for document in corpus:
        for fact in document["facts"]:
            records.append(
                {
                    "question": fact["question"],
                    "ground_truth": fact["answer"],
                    "reference_contexts": [document["text"]],
                    "metadata": {
                        "category": document["category"],
                        "document_id": document["id"],
                        "document_title": document["title"],
                        "source": "evalforge-synthetic-reference-v1",
                    },
                }
            )

    output = DATA_DIR / "golden_dataset.jsonl"
    lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} questions to {output}")


if __name__ == "__main__":
    main()
