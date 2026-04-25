import platform
from pathlib import Path
import shutil
from datetime import datetime


def executable_name() -> str:
    if platform.system().lower().startswith("win"):
        return "NailQue.exe"
    return "NailQue"


def main() -> int:
    root = Path(__file__).resolve().parent
    dist = root / "dist"
    exe = dist / executable_name()
    if not exe.exists():
        print(f"Executable not found: {exe}")
        print("Build first with platform build script.")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    release_dir = root / "release" / f"NailQue-{platform.system()}-{stamp}"
    release_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe, release_dir / exe.name)
    for file_name in [
        ".env.example",
        "PRODUCTION_READINESS.md",
        "BUILD_EXECUTABLES.md",
    ]:
        source = root / file_name
        if source.exists():
            shutil.copy2(source, release_dir / source.name)

    archive = shutil.make_archive(str(release_dir), "zip", root_dir=release_dir)
    print(f"Release folder: {release_dir}")
    print(f"Release zip: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
