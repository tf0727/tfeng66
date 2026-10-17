"""Local persisted vector retrieval. Deterministic character-bigram hashing, no downloads."""
import hashlib
import json
import math
import re
from db.models import KnowledgeEntry, KnowledgeVector, SessionLocal

def embed(text: str, dimensions: int = 256) -> list[float]:
    text = re.sub(r'\s+', '', text.lower())
    vector = [0.0] * dimensions
    tokens = [text[i:i+2] for i in range(max(0, len(text)-1))] + re.findall(r'[a-z]+', text)
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        vector[int.from_bytes(digest[:4], 'big') % dimensions] += 1.0
    norm = math.sqrt(sum(x*x for x in vector)) or 1
    return [x / norm for x in vector]

def index_entry(db, row):
    if row.status != 'approved':
        old = db.get(KnowledgeVector, row.id)
        if old: db.delete(old)
    else:
        db.merge(KnowledgeVector(entry_id=row.id, version=row.version, vector=json.dumps(embed(row.question + ' ' + row.answer))))

def knowledge_snapshot() -> list[dict]:
    with SessionLocal() as db:
        rows = db.query(KnowledgeEntry).filter_by(status='approved').order_by(KnowledgeEntry.id).all()
        return [{k: getattr(r, k) for k in ('id', 'question', 'answer', 'source', 'version')} for r in rows]

def search_knowledge(query: str, snapshot: list[dict] | None = None, limit: int = 4) -> dict:
    q = embed(query)
    if snapshot is None:
        with SessionLocal() as db:
            pairs = db.query(KnowledgeEntry, KnowledgeVector).join(KnowledgeVector, KnowledgeEntry.id == KnowledgeVector.entry_id).filter(KnowledgeEntry.status == 'approved', KnowledgeEntry.version == KnowledgeVector.version).all()
            rows = [({k: getattr(r, k) for k in ('id', 'question', 'answer', 'source', 'version')}, json.loads(v.vector)) for r,v in pairs]
    else:
        rows = [(r, embed(r['question'] + ' ' + r['answer'])) for r in snapshot]
    hits = [{**r, 'score': round(sum(a*b for a,b in zip(q,v)), 4)} for r,v in rows]
    hits = sorted((r for r in hits if r['score'] >= .12), key=lambda r: r['score'], reverse=True)[:limit]
    return {'matches': hits, 'reliable': bool(hits), 'index': 'local-sha256-bigram-256', 'note': '字符相似度不等于模型置信度，事实引用需要核对来源。'}
