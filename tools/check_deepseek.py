"""Live public-domain smoke test. No credentials or raw provider responses are printed."""

import json
from pathlib import Path

from storygal.review import Review
from storygal.storage import Store

root = Path(__file__).resolve().parents[1]
store = Store(root / "data/p1-live-check")
review = Review(store)
project = store.create(
    "孔明曰：「此都督病源也。」\n周瑜曰：「願先生賜教。」\n孔明笑曰：「亮有一方。」".encode(),
    "deepseek-smoke.txt",
    "public_domain",
    "utf-8",
)
result = review.analyze(project["id"])
state = review.state(project["id"])
report = {
    "project_id": project["id"],
    "provider": result["provider"],
    "model": result["model"],
    "requests": result["requests"],
    "usage": result["usage"],
    "characters": len(state["characters"]),
    "dialogues": len(state["dialogues"]),
    "manual_review_preserved": all(
        d["status"] == "pending" for d in state["dialogues"]
    ),
}
output = root / "data/verification/p1-deepseek.json"
output.parent.mkdir(exist_ok=True, parents=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
