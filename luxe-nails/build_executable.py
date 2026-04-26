import subprocess
import sys
from pathlib import Path


def _resolve_icon(root: Path) -> Path | None:
    icons_dir = root / "assets" / "icons"
    if sys.platform.startswith("win"):
        ico_icon = icons_dir / "app.ico"
        if ico_icon.exists():
            return ico_icon

        png_icon = icons_dir / "app-logo.png"
        if png_icon.exists():
            try:
                from PIL import Image
            except Exception:
                return None
            generated = root / "build" / "app.ico"
            generated.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(png_icon) as image:
                image.save(generated, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            return generated
        return None

    mac_icon = icons_dir / "app.icns"
    if mac_icon.exists():
        return mac_icon
    return None


def build() -> int:
    root = Path(__file__).resolve().parent
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data = []
    files_to_bundle = [
        "luxe-nails-queue.html",
        "luxe-nails-employee.html",
        "luxe-nails-mobile.html",
        "VERSION",
        "VERSION.windows",
        "VERSION.macos",
        ".env.example",
        "BUILD_EXECUTABLES.md",
    ]
    for rel in files_to_bundle:
        if (root / rel).exists():
            add_data.append(f"{rel}{sep}.")
    add_data.extend([
        f"assets/icons{sep}assets/icons",
        f"assets/sounds{sep}assets/sounds",
        f"assets/cursors{sep}assets/cursors",
    ])

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

    icon_file = _resolve_icon(root)
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
