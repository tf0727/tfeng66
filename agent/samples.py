"""Single source of truth for playbook tools and system context."""
import hashlib
import json
from db.models import SessionLocal, TrainingSample

def approved_samples() -> list[dict]:
    with SessionLocal() as db:
        rows = db.query(TrainingSample).filter_by(status='approved').order_by(TrainingSample.id).all()
        return [{k: getattr(row,k) for k in ('id','question','answer','reason','scene','source')} for row in rows]

def sample_version(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
