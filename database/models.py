import datetime
from sqlalchemy import (Column, Integer, String, BigInteger,
                        DateTime, ForeignKey, Float, Enum, Boolean)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=True)
    balance = Column(Float, default=0.0)
    hold_balance = Column(Float, default=0.0)
    referral_earnings = Column(Float, default=0.0)
    registration_date = Column(DateTime, default=datetime.datetime.utcnow)
    
    referrer_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    referrer = relationship("User", remote_side=[id])

    warnings = Column(Integer, default=0)
    google_cooldown_until = Column(DateTime, nullable=True)
    yandex_cooldown_until = Column(DateTime, nullable=True)
    gmail_cooldown_until = Column(DateTime, nullable=True)
    blocked_until = Column(DateTime, nullable=True)
    
    is_anonymous_in_stats = Column(Boolean, default=False, nullable=False)
    
    reviews = relationship("Review", back_populates="user")
    promo_activations = relationship("PromoActivation", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")


class Review(Base):
    __tablename__ = 'reviews'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    platform = Column(String)
    link_id = Column(Integer, ForeignKey('links.id'), nullable=True)
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    hold_until = Column(DateTime, nullable=True)
    amount = Column(Float, nullable=True)
    
    review_text = Column(String, nullable=True)
    admin_message_id = Column(BigInteger, nullable=True)
    
    link = relationship("Link")
    user = relationship("User", back_populates="reviews")


class Link(Base):
    __tablename__ = 'links'
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    platform = Column(String)
    status = Column(Enum('available', 'assigned', 'used', 'expired', name='link_status_enum'), default='available')
    assigned_to_user_id = Column(BigInteger, nullable=True)
    assigned_at = Column(DateTime, nullable=True)

class WithdrawalRequest(Base):
    __tablename__ = 'withdrawal_requests'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum('pending', 'approved', 'rejected', name='withdrawal_status_enum'), default='pending', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    recipient_info = Column(String, nullable=False)
    comment = Column(String, nullable=True)

    user = relationship("User")

# --- Таблицы для промокодов ---

class PromoCode(Base):
    __tablename__ = 'promo_codes'

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True, nullable=False)
    condition = Column(Enum('no_condition', 'google_review', 'yandex_review', 'gmail_account', name='promo_condition_enum'), nullable=False)
    reward = Column(Float, nullable=False)
    total_uses = Column(Integer, nullable=False)
    current_uses = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    activations = relationship("PromoActivation", back_populates="promo_code")


class PromoActivation(Base):
    __tablename__ = 'promo_activations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    promo_code_id = Column(Integer, ForeignKey('promo_codes.id'), nullable=False)
    status = Column(Enum('pending_condition', 'completed', 'cancelled', name='promo_status_enum'), default='pending_condition', nullable=False)
    activated_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="promo_activations")
    promo_code = relationship("PromoCode", back_populates="activations")

# --- НОВАЯ ТАБЛИЦА ДЛЯ СИСТЕМЫ ПОДДЕРЖКИ ---

class SupportTicket(Base):
    __tablename__ = 'support_tickets'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    username = Column(String, nullable=True)
    question = Column(String, nullable=False)
    
    # Сохраняем ID сообщений у обоих админов, чтобы их можно было отредактировать
    admin_message_id_1 = Column(BigInteger, nullable=True)
    admin_message_id_2 = Column(BigInteger, nullable=True)
    
    status = Column(Enum('open', 'claimed', 'closed', name='ticket_status_enum'), default='open', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Кто из админов ответил
    admin_id = Column(BigInteger, nullable=True)

    user = relationship("User", back_populates="support_tickets")