"""Create a source-only UpgradeLab archive for local testing."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "UpgradeLab-testing.zip"
EXCLUDED_DIRS = {
    ".git", ".artifacts", ".browser-profile", ".design", ".python", ".research",
    ".uv-cache", "__pycache__", ".venv", "venv", "node_modules", "dist", "build",
    "coverage", ".pytest_cache", ".mypy_cache", "storage", "uploads",
}
EXCLUDED_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".ods", ".log", ".pyc", ".zip",
}


def include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts[:-1]):
        return False
    if path.name == ".env.testing.example":
        return True
    if path.name == ".env" or path.name.startswith(".env."):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith(("-wal", "-shm")):
        return False
    return path.is_file()


def main() -> None:
    files = sorted(path for path in ROOT.rglob("*") if include(path))
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=7) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        forbidden = [name for name in names if Path(name).name == ".env" or name.endswith((".db", ".sqlite", ".sqlite3", ".xlsx", ".xls"))]
        if forbidden:
            ARCHIVE.unlink(missing_ok=True)
            raise RuntimeError(f"Unsafe files found in archive: {forbidden}")
    print(f"Created {ARCHIVE} ({len(files)} files, {ARCHIVE.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
