import os
import subprocess
import sys
from pathlib import Path


def build() -> int:
    root = Path(__file__).resolve().parent
    sep = ":"
    add_data = [
        f"luxe-nails-queue.html{sep}.",
        f"luxe-nails-employee.html{sep}.",
        f"luxe-nails-mobile.html{sep}.",
        f"VERSION{sep}.",
        f".env.example{sep}.",
        f"BUILD_EXECUTABLES.md{sep}.",
        f"assets/icons{sep}assets/icons",
        f"assets/sounds{sep}assets/sounds",
        f"assets/cursors{sep}assets/cursors",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "NailQue",
        "--collect-all",
        "flask",
        "--collect-all",
        "dotenv",
        "--collect-all",
        "webview",
    ]

    # Optional macOS app icon
    icon_file = None
    candidate = root / "assets" / "icons" / "app.icns"
    if candidate.exists():
        icon_file = candidate
    if icon_file:
        cmd.extend(["--icon", str(icon_file)])

    for item in add_data:
        cmd.extend(["--add-data", item])
    cmd.append("app.py")

    print("Building executable with command:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(root), check=False)

    if result.returncode == 0:
        dist_dir = root / "dist"
        print("\nBuild complete.")
        print(f"Executable output: {dist_dir}")
        print(f"Run: {dist_dir / 'NailQue'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(build())
