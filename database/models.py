# file: database/models.py

import datetime
from sqlalchemy import (Column, Integer, String, BigInteger,
                        DateTime, ForeignKey, Float, Enum, Boolean) # <-- ДОБАВЛЕН Boolean
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
    blocked_until = Column(DateTime, nullable=True)

    # ДОБАВЛЕНО: Новое поле для анонимности в статистике
    is_anonymous_in_stats = Column(Boolean, default=False, nullable=False)
    
    reviews = relationship("Review", back_populates="user")


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