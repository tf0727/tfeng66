import json
from threading import RLock
from uuid import uuid4
from db.models import Ticket, SessionLocal

_lock = RLock()

def create_ticket(session_id: str, reason: str, summary: str, student_profile: dict | None = None, confidence: float | None = None) -> dict:
    if not session_id: raise ValueError('转人工必须绑定会话')
    with _lock, SessionLocal() as db:
        row = db.query(Ticket).filter(Ticket.session_id == session_id, Ticket.status != 'resolved').first()
        if not row:
            row = Ticket(id='T'+uuid4().hex[:12].upper(), session_id=session_id, reason=reason, summary=summary[:200], profile=json.dumps(student_profile or {}, ensure_ascii=False), confidence='' if confidence is None else str(confidence))
            db.add(row); db.commit()
        return {'ticket_id': row.id, 'status': row.status, 'reason': row.reason, 'summary': row.summary, 'student_profile': json.loads(row.profile), 'confidence': row.confidence}
