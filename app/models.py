from datetime import datetime, date, timezone
from sqlalchemy import String, Integer, Boolean, Text, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(130))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    institutional_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    course: Mapped[str] = mapped_column(String(120), default='')
    period: Mapped[str] = mapped_column(String(30), default='')
    city: Mapped[str] = mapped_column(String(120), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    skills: Mapped[str] = mapped_column(Text, default='')
    experience: Mapped[str] = mapped_column(Text, default='')
    education: Mapped[str] = mapped_column(Text, default='')
    languages: Mapped[str] = mapped_column(Text, default='')
    certificates: Mapped[str] = mapped_column(Text, default='')
    linkedin: Mapped[str] = mapped_column(String(400), default='')
    portfolio: Mapped[str] = mapped_column(String(400), default='')
    contact_public: Mapped[bool] = mapped_column(Boolean, default=False)
    avatar_file: Mapped[str] = mapped_column(String(100), default='')
    resume_file: Mapped[str] = mapped_column(String(100), default='')
    company_name: Mapped[str] = mapped_column(String(160), default='')
    cnpj: Mapped[str] = mapped_column(String(20), default='')
    industry: Mapped[str] = mapped_column(String(120), default='')
    website: Mapped[str] = mapped_column(String(400), default='')
    consent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    jobs: Mapped[list['Job']] = relationship(back_populates='company', foreign_keys='Job.company_id')

class EmailToken(Base):
    __tablename__ = 'email_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(String(35))
    area: Mapped[str] = mapped_column(String(90))
    requirements: Mapped[str] = mapped_column(Text, default='')
    benefits: Mapped[str] = mapped_column(Text, default='')
    compensation: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(120))
    work_mode: Mapped[str] = mapped_column(String(20))
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    company: Mapped[User] = relationship(back_populates='jobs', foreign_keys=[company_id])
    applications: Mapped[list['Application']] = relationship(back_populates='job', cascade='all, delete-orphan')

class Application(Base):
    __tablename__ = 'applications'
    __table_args__ = (UniqueConstraint('job_id', 'applicant_id', name='uq_application_job_applicant'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(30), default='enviada')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applicant: Mapped[User] = relationship(foreign_keys=[applicant_id])
    job: Mapped[Job] = relationship(back_populates='applications')
    messages: Mapped[list['Message']] = relationship(back_populates='application', cascade='all, delete-orphan')

class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    application: Mapped[Application] = relationship(back_populates='messages')
    sender: Mapped[User] = relationship()

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(140), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
