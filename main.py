from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import DateTime, String, Text, create_engine, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'wedding.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass

class GuestChoice(Base):
    __tablename__ = "guest_choices"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    main_dish: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    alcohol: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
class GuestChoiceRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True
    )

    first_name: str = Field(
        ...,
        alias="firstName",
        min_length=1,
        max_length=100,
    )

    last_name: str = Field(
        ...,
        alias="lastName",
        min_length=1,
        max_length=100,
    )

    main_dish: str = Field(
        ...,
        alias="mainDish",
        min_length=1,
        max_length=100,
    )

    alcohol: list[str] = Field(
        default_factory=list,
        max_length=10,
    )

    comment: str | None = Field(
        default=None,
        max_length=2000,
    )

    submitted_at: datetime | None = Field(
        default=None,
        alias="submittedAt",
    )

def create_database() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_database()
    yield


app = FastAPI(
    title="Выбор блюд на свадебный банкет",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
def show_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "success": False,
            "error": None,
        },
    )


@app.post("/")
def submit_form(
    payload: GuestChoiceRequest,
    db: Session = Depends(get_db),
):
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    main_dish = payload.main_dish.strip()
    comment = (payload.comment or "").strip()

    ALLOWED_DISHES = {
    "Медальоны из говядины",
    "Филе лосося",
    "Равиоли с белыми грибами",
    }

    ALLOWED_ALCOHOL = {
    "Вино",
    "Игристое вино",
    "Крепкие напитки",
    "Без алкоголя",
    }

    alcohol = [
        item.strip()
        for item in payload.alcohol
        if item.strip()
    ]

    if not first_name or not last_name:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Укажите имя и фамилию гостя.",
            },
        )

    if main_dish not in ALLOWED_DISHES:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Выберите корректное основное блюдо.",
            },
        )

    invalid_alcohol = [
        item
        for item in alcohol
        if item not in ALLOWED_ALCOHOL
    ]

    if invalid_alcohol:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": (
                    "Выбран некорректный вариант алкоголя: "
                    + ", ".join(invalid_alcohol)
                ),
            },
        )

    submitted_at = payload.submitted_at

    if submitted_at is not None:
        submitted_at = submitted_at.astimezone(timezone.utc).replace(
            tzinfo=None
        )
    else:
        submitted_at = datetime.utcnow()

    guest_choice = GuestChoice(
        first_name=first_name,
        last_name=last_name,
        main_dish=main_dish,
        alcohol=", ".join(alcohol) if alcohol else "Не выбран",
        comments=comment or None,
        created_at=submitted_at,
    )

    db.add(guest_choice)
    db.commit()
    db.refresh(guest_choice)

    return {
        "success": True,
        "message": "Ваш выбор успешно сохранён.",
        "id": guest_choice.id,
    }


@app.get("/admin/choices")
def get_choices(db: Session = Depends(get_db)):
    choices = (
        db.query(GuestChoice)
        .order_by(GuestChoice.created_at.desc())
        .all()
    )

    return [
        {
            "id": choice.id,
            "last_name": choice.last_name,
            "first_name": choice.first_name,
            "main_dish": choice.main_dish,
            "alcohol": choice.alcohol,
            "comments": choice.comments,
            "created_at": choice.created_at.isoformat(),
        }
        for choice in choices
    ]