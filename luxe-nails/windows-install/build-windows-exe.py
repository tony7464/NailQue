import subprocess
import sys
from pathlib import Path


def build() -> int:
    root = Path(__file__).resolve().parent

    add_data = [
        "luxe-nails-queue.html;.",
        "luxe-nails-employee.html;.",
        "assets/cursors;assets/cursors",
        "assets/icons;assets/icons",
        "assets/sounds;assets/sounds",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "NailQue",
        "--collect-all",
        "flask",
        "--collect-all",
        "dotenv",
        "--collect-all",
        "webview",
    ]

    for entry in add_data:
        cmd.extend(["--add-data", entry])

    cmd.append("app.py")

    print("Building Windows executable...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(root), check=False)

    if result.returncode == 0:
        print("\nBuild complete.")
        print(f"Executable: {root / 'dist' / 'NailQue.exe'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(build())
