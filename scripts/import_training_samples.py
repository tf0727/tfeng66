"""Import annotated samples transactionally, without duplicating existing rows."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.models import SessionLocal, TrainingSample


def main():
    items = json.loads((ROOT / "data/training_samples_import.json").read_text(encoding="utf-8"))
    added, existing = [], []
    with SessionLocal() as db:
        for item in items:
            row = db.query(TrainingSample).filter_by(
                question=item["question"], answer=item["answer"], reason=item["reason"]
            ).first()
            if row:
                existing.append(row.id)
                continue
            row = TrainingSample(**item, status="pending")
            db.add(row)
            db.flush()
            added.append(row.id)
        db.commit()
        ids = added + existing
        count = db.query(TrainingSample).filter(TrainingSample.id.in_(ids)).count()
        assert count == len(items), "导入数量不匹配"
    print(json.dumps({"added": len(added), "existing": len(existing), "verified": count, "ids": ids}, ensure_ascii=False))


if __name__ == "__main__":
    main()
