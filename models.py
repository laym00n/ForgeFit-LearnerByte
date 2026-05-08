from datetime import UTC, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def now_utc():
    return datetime.now(UTC)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    activity_level = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

    chat_messages = db.relationship(
        "ChatMessage", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def has_onboarded(self):
        return all(
            value is not None
            for value in [self.age, self.height_cm, self.weight_kg, self.gender, self.activity_level]
        )


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    agent_id = db.Column(db.String(10), nullable=False, index=True)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False, index=True)

    user = db.relationship("User", back_populates="chat_messages")
