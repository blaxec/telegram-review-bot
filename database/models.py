# file: database/models.py

import datetime
from sqlalchemy import (Column, Integer, String, BigInteger, JSON,
                        DateTime, ForeignKey, Float, Enum, Boolean, Text)
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

    referral_path = Column(String, nullable=True)
    referral_subpath = Column(String, nullable=True)

    warnings = Column(Integer, default=0)
    google_cooldown_until = Column(DateTime, nullable=True)
    yandex_with_text_cooldown_until = Column(DateTime, nullable=True)
    yandex_without_text_cooldown_until = Column(DateTime, nullable=True)
    gmail_cooldown_until = Column(DateTime, nullable=True)
    blocked_until = Column(DateTime, nullable=True)
    
    is_anonymous_in_stats = Column(Boolean, default=False, nullable=False)
    
    is_banned = Column(Boolean, default=False, nullable=False)
    banned_at = Column(DateTime, nullable=True)
    ban_reason = Column(String, nullable=True)
    last_unban_request_at = Column(DateTime, nullable=True)
    unban_count = Column(Integer, default=0, nullable=False)
    
    phone_number = Column(String, nullable=True)

    support_warnings = Column(Integer, default=0, nullable=False)
    support_cooldown_until = Column(DateTime, nullable=True)
    
    dnd_enabled = Column(Boolean, default=False, nullable=False)
    
    is_intern = Column(Boolean, default=False, nullable=False)
    is_busy_intern = Column(Boolean, default=False, nullable=False)


    reviews = relationship("Review", back_populates="user")
    promo_activations = relationship("PromoActivation", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")
    operations = relationship("OperationHistory", back_populates="user")
    unban_requests = relationship("UnbanRequest", back_populates="user")
    
    internship_application = relationship("InternshipApplication", back_populates="user", uselist=False, cascade="all, delete-orphan")
    internship_tasks = relationship("InternshipTask", back_populates="intern")
    internship_mistakes = relationship("InternshipMistake", back_populates="intern")


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
    screenshot_file_id = Column(String, nullable=True)
    
    confirmation_screenshot_file_id = Column(String, nullable=True)
    attached_photo_file_id = Column(String, nullable=True)
    
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
    is_fast_track = Column(Boolean, default=False, nullable=False)
    requires_photo = Column(Boolean, default=False, nullable=False)


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

class SupportTicket(Base):
    __tablename__ = 'support_tickets'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    username = Column(String, nullable=True)
    question = Column(String, nullable=False)
    
    admin_message_id_1 = Column(BigInteger, nullable=True)
    admin_message_id_2 = Column(BigInteger, nullable=True)
    
    photo_file_id = Column(String, nullable=True)
    
    status = Column(Enum('open', 'claimed', 'closed', name='ticket_status_enum'), default='open', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    admin_id = Column(BigInteger, nullable=True)

    user = relationship("User", back_populates="support_tickets")

class RewardSetting(Base):
    __tablename__ = 'reward_settings'
    place = Column(Integer, primary_key=True)
    reward_amount = Column(Float, nullable=False)

class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    
class OperationHistory(Base):
    __tablename__ = 'operation_history'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    operation_type = Column(Enum(
        'REVIEW_APPROVED', 'PROMO_ACTIVATED', 'WITHDRAWAL', 'FINE', 
        'TRANSFER_SENT', 'TRANSFER_RECEIVED', 'TOP_REWARD',
        name='operation_type_enum'
    ), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Новые поля для переводов
    comment = Column(Text, nullable=True)
    media_json = Column(Text, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    sender_id = Column(BigInteger, nullable=True)

    user = relationship("User", back_populates="operations")
    sender = relationship("User", foreign_keys=[sender_id])
    complaints = relationship("TransferComplaint", back_populates="transfer")

class UnbanRequest(Base):
    __tablename__ = 'unban_requests'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    reason = Column(String, nullable=False)
    status = Column(Enum('pending', 'approved', 'rejected', 'payment_pending', name='unban_request_status_enum'), default='pending', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reviewed_by_admin_id = Column(BigInteger, nullable=True)
    
    user = relationship("User", back_populates="unban_requests")

class InternshipApplication(Base):
    __tablename__ = 'internship_applications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), unique=True, nullable=False)
    username = Column(String, nullable=True)
    age = Column(String, nullable=False)
    hours_per_day = Column(String, nullable=False)
    response_time = Column(String, nullable=True)
    platforms = Column(String, nullable=False)
    status = Column(Enum('pending', 'approved', 'rejected', 'archived_success', name='internship_app_status_enum'), default='pending', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="internship_application")

class InternshipTask(Base):
    __tablename__ = 'internship_tasks'
    
    id = Column(Integer, primary_key=True)
    intern_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    platform = Column(String, nullable=False)
    task_type = Column(String, nullable=False)
    goal_count = Column(Integer, nullable=False)
    current_progress = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    estimated_salary = Column(Float, default=0.0)
    status = Column(Enum('active', 'completed', 'fired', name='internship_task_status_enum'), default='active', nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_task_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    intern = relationship("User", back_populates="internship_tasks")
    mistakes = relationship("InternshipMistake", back_populates="task", cascade="all, delete-orphan")

class InternshipMistake(Base):
    __tablename__ = 'internship_mistakes'
    
    id = Column(Integer, primary_key=True)
    intern_task_id = Column(Integer, ForeignKey('internship_tasks.id'), nullable=False)
    intern_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    review_id = Column(Integer, nullable=True)
    reason = Column(String, nullable=False)
    penalty_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    task = relationship("InternshipTask", back_populates="mistakes")
    intern = relationship("User", back_populates="internship_mistakes")

# --- НОВЫЕ ТАБЛИЦЫ ---

class Administrator(Base):
    __tablename__ = 'administrators'

    user_id = Column(BigInteger, primary_key=True)
    role = Column(Enum('admin', 'super_admin', name='admin_role_enum'), nullable=False, default='admin')
    is_tester = Column(Boolean, nullable=False, default=False)
    is_removable = Column(Boolean, nullable=False, default=True) 
    added_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class PostTemplate(Base):
    __tablename__ = 'post_templates'
    
    id = Column(Integer, primary_key=True)
    template_name = Column(String, unique=True, nullable=False)
    text = Column(Text, nullable=True)
    media_json = Column(Text, nullable=True)
    created_by = Column(BigInteger, nullable=False)

class TransferComplaint(Base):
    __tablename__ = 'transfer_complaints'

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey('operation_history.id'), nullable=False)
    complainant_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(Enum('pending', 'reviewed', name='complaint_status_enum'), default='pending', nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    transfer = relationship("OperationHistory", back_populates="complaints")
    complainant = relationship("User", foreign_keys=[complainant_id])