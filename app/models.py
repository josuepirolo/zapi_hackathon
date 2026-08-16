"""Modelo de dados minimo: Campaign, Contact.

Ver `.sdds/specs/consentimento-grupo.spec.md` secao 16 e
`.sdds/contracts/consentimento-grupo.contract.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class MembershipStatus(StrEnum):
    NONE = "NONE"
    ADDED = "ADDED"
    REMOVED = "REMOVED"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    whatsapp_group_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # So responde/inicia consentimento se a mensagem de um contato novo
    # contiver essa palavra (case-insensitive) - sem isso, QUALQUER mensagem
    # de QUALQUER numero desconhecido virava convite automatico (incidente
    # real: mensagens saindo pra contatos nao relacionados ao hackathon).
    trigger_keyword: Mapped[str] = mapped_column(String, nullable=False)
    invitation_message: Mapped[str] = mapped_column(String, nullable=False)
    welcome_message: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="campaign")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    chat_lid: Mapped[str] = mapped_column(String, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    consent_status: Mapped[ConsentStatus] = mapped_column(String, default=ConsentStatus.PENDING)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    membership_status: Mapped[MembershipStatus] = mapped_column(String, default=MembershipStatus.NONE)
    # True enquanto aguarda confirmacao SIM/NAO do fluxo #sairgrupozapi -
    # ver app/webhook.py.
    removal_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    # Reflete group-add-admin/group-remove-admin disparados pelo painel -
    # ver app/admin_api.py.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="contacts")


class ChatLinkStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class ChatConsentSession(Base):
    """Consentimento via link trackeado no chat publico (/promocoes)."""

    __tablename__ = "chat_consent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    browser_session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    status: Mapped[ChatLinkStatus] = mapped_column(String, default=ChatLinkStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
