import hashlib
import hmac
import json
import secrets
import re
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.api.deps import DBSession
from app.db.models import User, LoginSession, SavedBuild
from app.schemas.calculate import CalculateRequest
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["account"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = True

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Укажите корректный email")
        return value


class Registration(Credentials):
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=80)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Введите имя")
        return value.strip()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def current_user(db: DBSession, request: Request, upgrade_session: str | None = Cookie(default=None)):
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins_list and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Недопустимый источник запроса")
    token = hashlib.sha256((upgrade_session or "").encode()).hexdigest()
    session = db.get(LoginSession, token)
    if not session or session.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Войдите в аккаунт")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, "Войдите в аккаунт")
    return user


AuthUser = Annotated[User, Depends(current_user)]


def public_user(user):
    return {"id": user.id, "name": user.name, "email": user.email}


def sign_in(db, user, response, remember=True):
    token = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= datetime.utcnow()))
    db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                        expires_at=datetime.utcnow() + timedelta(days=30 if remember else 1)))
    db.commit()
    response.set_cookie("upgrade_session", token, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, max_age=2592000 if remember else None, path="/")
    response.headers["Cache-Control"] = "no-store"
    return public_user(user)


@router.post("/auth/register", status_code=201)
def register(payload: Registration, db: DBSession, response: Response):
    salt = secrets.token_hex(16)
    user = User(email=payload.email, name=payload.name, password_hash=salt + ":" + password_hash(payload.password, salt))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Этот email уже зарегистрирован")
    return sign_in(db, user, response, payload.remember_me)


@router.post("/auth/login")
def login(payload: Credentials, db: DBSession, response: Response):
    user = db.scalar(select(User).where(User.email == payload.email))
    salt, expected = user.password_hash.split(":") if user else ("00" * 16, "00" * 64)
    valid = hmac.compare_digest(password_hash(payload.password, salt), expected)
    if not user or not valid:
        raise HTTPException(401, "Неверный email или пароль")
    return sign_in(db, user, response, payload.remember_me)


@router.get("/auth/me")
def me(user: AuthUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return public_user(user)


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.patch("/auth/profile")
def update_profile(payload: ProfileUpdate, db: DBSession, user: AuthUser):
    if len(payload.name.strip()) < 2:
        raise HTTPException(422, "Имя должно содержать хотя бы два символа")
    user.name = payload.name.strip()
    db.commit()
    return public_user(user)


@router.post("/auth/password")
def update_password(payload: PasswordUpdate, db: DBSession, user: AuthUser, response: Response):
    salt, expected = user.password_hash.split(":")
    if not hmac.compare_digest(password_hash(payload.current_password, salt), expected):
        raise HTTPException(400, "Текущий пароль указан неверно")
    salt = secrets.token_hex(16)
    user.password_hash = salt + ":" + password_hash(payload.new_password, salt)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    return sign_in(db, user, response)


@router.post("/auth/logout", status_code=204)
def logout(db: DBSession, user: AuthUser, response: Response, upgrade_session: str | None = Cookie(default=None)):
    session = db.get(LoginSession, hashlib.sha256((upgrade_session or "").encode()).hexdigest())
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie("upgrade_session", path="/")


@router.get("/builds")
def builds(db: DBSession, user: AuthUser):
    return [{"id": b.id, "created_at": b.created_at, **json.loads(b.data)} for b in
            db.scalars(select(SavedBuild).where(SavedBuild.user_id == user.id).order_by(SavedBuild.id.desc()))]


@router.post("/builds", status_code=201)
def save_build(payload: CalculateRequest, db: DBSession, user: AuthUser):
    from app.api.calculate import post_calculate
    result = post_calculate(payload, db)
    build = SavedBuild(user_id=user.id, data=json.dumps({"config": payload.model_dump(mode="json"), "result": result.model_dump(mode="json")}, ensure_ascii=False))
    db.add(build)
    db.commit()
    return {"id": build.id}


@router.delete("/builds/{build_id}", status_code=204)
def delete_build(build_id: int, db: DBSession, user: AuthUser):
    build = db.get(SavedBuild, build_id)
    if not build or build.user_id != user.id:
        raise HTTPException(404, "Сборка не найдена")
    db.delete(build)
    db.commit()
