import shutil
from pathlib import Path


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def main() -> int:
    root = Path(__file__).resolve().parent
    win = root / "windows-install"

    files_to_copy = [
        "app.py",
        "luxe-nails-queue.html",
        "luxe-nails-employee.html",
        "luxe-nails-mobile.html",
        ".env.example",
        "VERSION",
    ]
    for rel in files_to_copy:
        copy_file(root / rel, win / rel)

    copy_tree(root / "assets", win / "assets")

    print("Windows bundle synced from current project files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
