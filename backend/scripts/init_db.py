import json
import random
from pathlib import Path
from app.db.base import Base, engine, SessionLocal
from app.db.models import Hardware

SEED_PATH = Path(__file__).resolve().parent.parent / "seed_data.json"


def _normalize(score: int, lo: int, hi: int) -> int:
    if hi == lo:
        return 55
    value = 10 + (score - lo) * 90 / (hi - lo)
    return max(10, min(100, round(value)))


def _generate_price(raw_score: int, hw_type: str) -> int:
    """Генерирует правдоподобную цену на основе PassMark"""
    if hw_type == "CPU":
        # Условно: 1000 баллов = 1500 руб.
        base_price = int((raw_score / 1000) * 1500)
    else:
        # Видеокарты дороже: 1000 баллов = 2000 руб.
        base_price = int((raw_score / 1000) * 2000)
        
    # Добавляем случайный разброс +/- 10%, чтобы цены не были одинаковыми
    variation = random.uniform(0.9, 1.1)
    final_price = int(base_price * variation)
    
    # Округляем до сотен (например, 12345 -> 12300)
    return (final_price // 100) * 100


def seed() -> None:
    Base.metadata.create_all(bind=engine)

    if not SEED_PATH.exists():
        raise SystemExit(f"Файл {SEED_PATH} не найден.")

    raw = SEED_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(f"Файл {SEED_PATH} пустой.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Невалидный JSON: {exc.msg} (строка {exc.lineno})") from exc

    db = SessionLocal()
    try:
        db.query(Hardware).delete()
        db.commit()

        for hw_type, key in (("CPU", "cpus"), ("GPU", "gpus")):
            items = data.get(key, [])
            if not items:
                continue
            scores = [int(item["score"]) for item in items]
            lo, hi = min(scores), max(scores)
            for item in items:
                raw_score = int(item["score"])
                db.add(
                    Hardware(
                        type=hw_type,
                        name=item["name"],
                        raw_score=raw_score,
                        normalized_score=_normalize(raw_score, lo, hi),
                        cores=item.get("cores"),
                        avg_price=_generate_price(raw_score, hw_type) # <-- ГЕНЕРИРУЕМ ЦЕНУ
                    )
                )
        db.commit()
        total = db.query(Hardware).count()
        print(f"OK. Загружено записей Hardware: {total}")
        print("Цены сгенерированы на основе PassMark.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()