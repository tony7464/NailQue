import subprocess
import sys
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_icon(root: Path) -> Optional[Path]:
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


def _platform_version_file(root: Path) -> Path:
    if sys.platform.startswith("win"):
        return root / "platforms" / "windows" / "VERSION"
    return root / "platforms" / "macos" / "VERSION"


def build() -> int:
    root = _repo_root()
    sep = ";" if sys.platform.startswith("win") else ":"
    add_data = [
        f"web{sep}web",
        f"assets{sep}assets",
    ]
    version_file = _platform_version_file(root)
    if version_file.exists():
        add_data.append(f"{version_file.relative_to(root).as_posix()}{sep}.")
    env_example = root / ".env.example"
    if env_example.exists():
        add_data.append(f".env.example{sep}.")

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
        "--paths",
        str(root / "src"),
        "--collect-submodules",
        "nailque",
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
    cmd.append(str(root / "src" / "nailque" / "__main__.py"))

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
