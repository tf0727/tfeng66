from datetime import datetime, timezone
from pathlib import Path
import os
from dotenv import load_dotenv

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()
DB_PATH = Path(os.getenv("APP_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "app.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    profile: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(100), default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=0)

class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    reason: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    profile: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    confidence: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[str] = mapped_column(String(10))
    comment: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[int] = mapped_column(Integer, default=0)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")

class PromptProposal(Base):
    __tablename__ = "prompt_proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_version: Mapped[int] = mapped_column(Integer)
    diff: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    candidate: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    feedback_ids: Mapped[str] = mapped_column(Text, default="[]")

class TrainingSample(Base):
    __tablename__ = "training_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    scene: Mapped[str] = mapped_column(String(80), default="通用")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source: Mapped[str] = mapped_column(Text, default="人工录入")
    reviewer: Mapped[str] = mapped_column(String(80), default="")
    reviewed_at: Mapped[str] = mapped_column(String(50), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")

class ChatRun(Base):
    __tablename__ = "chat_runs"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="running")
    cancel: Mapped[int] = mapped_column(Integer, default=0)
    events: Mapped[str] = mapped_column(Text, default="[]")
    prompt_version: Mapped[int] = mapped_column(Integer, default=0)
    prompt_snapshot: Mapped[str] = mapped_column(Text, default="")
    knowledge_snapshot: Mapped[str] = mapped_column(Text, default="[]")
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    reply: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(30), default="model")
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewer: Mapped[str] = mapped_column(String(80), default="")
    reviewed_at: Mapped[str] = mapped_column(String(50), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")

class KnowledgeVector(Base):
    __tablename__ = "knowledge_vectors"
    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    vector: Mapped[str] = mapped_column(Text)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(80), default="本地管理员")
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())

class Replay(Base):
    __tablename__ = "replays"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[int] = mapped_column(Integer)
    knowledge_mode: Mapped[str] = mapped_column(String(30))
    knowledge_snapshot: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    trace: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())

Base.metadata.create_all(engine)
with engine.begin() as connection:
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(training_samples)")}
    if "reason" not in columns:
        connection.exec_driver_sql("ALTER TABLE training_samples ADD COLUMN reason TEXT DEFAULT ''")
    migrations = {
        "sessions": {"profile": "TEXT DEFAULT '{}'"},
        "messages": {"request_id": "TEXT DEFAULT ''", "prompt_version": "INTEGER DEFAULT 0"},
        "tickets": {"confidence": "TEXT DEFAULT ''", "created_at": "TEXT DEFAULT ''"},
        "feedback": {"prompt_version": "INTEGER DEFAULT 0", "proposal_id": "INTEGER"},
        "prompt_proposals": {"candidate": "TEXT DEFAULT ''", "rationale": "TEXT DEFAULT ''", "feedback_ids": "TEXT DEFAULT '[]'"},
        "training_samples": {"source": "TEXT DEFAULT '人工录入'", "reviewer": "TEXT DEFAULT ''", "reviewed_at": "TEXT DEFAULT ''", "review_note": "TEXT DEFAULT ''"},
    }
    for table, additions in migrations.items():
        existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
        for name, definition in additions.items():
            if name not in existing:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
