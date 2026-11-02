import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from app.api.deps import DBSession
from app.api.account import Credentials, password_hash
from app.db.base import SessionLocal
from app.db.models import User, PasswordReset, LoginSession, ResetRequestLimit
from app.services import mail

router = APIRouter(prefix="/api/auth", tags=["account"])
logger = logging.getLogger(__name__)


class ForgotPassword(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return Credentials.valid_email(value)


class ResetPassword(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(db, key, maximum):
    now = datetime.utcnow()
    key = digest(key)
    db.execute(delete(ResetRequestLimit).where(ResetRequestLimit.started_at < now - timedelta(hours=1)))
    row = db.get(ResetRequestLimit, key)
    if row is None:
        db.add(ResetRequestLimit(key_hash=key, started_at=now, attempts=1))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")
    else:
        changed = db.execute(update(ResetRequestLimit).where(
            ResetRequestLimit.key_hash == key, ResetRequestLimit.attempts < maximum
        ).values(attempts=ResetRequestLimit.attempts + 1)).rowcount
        db.commit()
        if not changed:
            raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")


def deliver(address, token):
    try:
        mail.send_reset_email(address, token)
    except Exception:
        # Never log email contents, reset URLs, credentials or tokens.
        logger.error("Password recovery email delivery failed; check SMTP configuration")
        with SessionLocal() as db:
            db.execute(delete(PasswordReset).where(PasswordReset.token_hash == digest(token)))
            db.commit()


@router.get("/recovery/status")
def recovery_status():
    return {"enabled": mail.configured()}


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPassword, db: DBSession, request: Request, response: Response, tasks: BackgroundTasks):
    response.headers["Cache-Control"] = "no-store"
    if not mail.configured():
        raise HTTPException(503, "Отправка писем пока не настроена. Обратитесь к администратору.")
    email = payload.email
    throttle(db, "ip:" + (request.client.host if request.client else "unknown"), 10)
    throttle(db, "email:" + email, 3)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        token = secrets.token_urlsafe(32)
        db.execute(delete(PasswordReset).where(PasswordReset.expires_at <= datetime.utcnow()))
        db.add(PasswordReset(token_hash=digest(token), user_id=user.id, expires_at=datetime.utcnow() + timedelta(minutes=30)))
        db.commit()
        tasks.add_task(deliver, user.email, token)
    return {"message": "Если аккаунт с таким email существует, письмо со ссылкой будет отправлено. Проверьте входящие и папку «Спам»."}


@router.post("/reset-password")
def reset_password(payload: ResetPassword, db: DBSession, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    throttle(db, "reset-ip:" + (request.client.host if request.client else "unknown"), 20)
    user_id = db.execute(delete(PasswordReset).where(
        PasswordReset.token_hash == digest(payload.token), PasswordReset.expires_at > datetime.utcnow()
    ).returning(PasswordReset.user_id)).scalar_one_or_none()
    if user_id is None:
        db.rollback()
        raise HTTPException(400, "Ссылка недействительна или истекла. Запросите новое письмо.")
    user = db.get(User, user_id)
    salt = secrets.token_hex(16)
    user.password_hash = salt + ":" + password_hash(payload.new_password, salt)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    db.commit()
    response.delete_cookie("upgrade_session", path="/")
    return {"message": "Пароль изменён. Войдите с новым паролем."}
