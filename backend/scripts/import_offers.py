"""Import sourced marketplace offers: python -m scripts.import_offers path.json"""
import argparse
from app.db.base import SessionLocal
from app.services.offers import load_offer_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filename")
    args = parser.parse_args()
    from app.main import app  # Ensure schema exists.
    with SessionLocal() as db:
        print("Imported offers:", load_offer_file(db, args.filename))
