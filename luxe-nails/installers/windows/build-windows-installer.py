import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    print(">", " ".join(command))
    result = subprocess.run(command, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")


def load_version(root: Path) -> str:
    version_candidates = [root / "VERSION.windows", root / "VERSION"]
    for version_file in version_candidates:
        if not version_file.exists():
            continue
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    raise RuntimeError("Missing version value. Create VERSION.windows (or VERSION as fallback).")


def safe_version_for_filename(version: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", version)


def locate_iscc() -> Path:
    env_iscc = (os.environ.get("INNO_SETUP_ISCC") or "").strip()
    if env_iscc:
        candidate = Path(env_iscc)
        if candidate.exists():
            return candidate
    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "Inno Setup was not found. Install Inno Setup 6 or set INNO_SETUP_ISCC to your ISCC.exe path."
    )


def build_standalone_zip(exe_path: Path, out_dir: Path, version: str, work_dir: Path) -> Path:
    portable_dir = work_dir / "portable" / f"NailQue-Windows-Standalone-{safe_version_for_filename(version)}"
    if portable_dir.exists():
        shutil.rmtree(portable_dir)
    portable_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe_path, portable_dir / "NailQue.exe")
    readme = portable_dir / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "NailQue Windows Standalone",
                "",
                "Run NailQue.exe to launch the app.",
                "Runtime files and logs are stored in %APPDATA%\\NailQue.",
                "",
                "For managed installation, use the NailQue-Setup installer instead.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    archive_base = out_dir / f"NailQue-Windows-Standalone-{safe_version_for_filename(version)}"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=portable_dir)
    return Path(archive_path)


def write_iss_script(exe_path: Path, out_dir: Path, work_dir: Path, version: str) -> Path:
    iss_path = work_dir / "NailQue-Setup.iss"
    output_base = f"NailQue-Setup-{safe_version_for_filename(version)}"
    contents = f"""[Setup]
AppId={{{{B7620497-D91D-4E4A-A8D4-CC9750C28CA8}}}}
AppName=NailQue
AppVersion={version}
AppPublisher=NailQue
DefaultDirName={{autopf}}\\NailQue
DefaultGroupName=NailQue
OutputDir={str(out_dir)}
OutputBaseFilename={output_base}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={{app}}\\NailQue.exe
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{str(exe_path)}"; DestDir: "{{app}}"; DestName: "NailQue.exe"; Flags: ignoreversion

[Icons]
Name: "{{group}}\\NailQue"; Filename: "{{app}}\\NailQue.exe"
Name: "{{autodesktop}}\\NailQue"; Filename: "{{app}}\\NailQue.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\NailQue.exe"; Description: "Launch NailQue"; Flags: nowait postinstall skipifsilent
"""
    iss_path.write_text(contents, encoding="utf-8")
    return iss_path


def main() -> int:
    if not sys.platform.startswith("win"):
        print("This script must be run on Windows.")
        return 1

    root = Path(__file__).resolve().parents[2]
    out_dir = root / "dist-installers"
    work_dir = root / "installer-work" / "windows"
    dist_dir = root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    version = load_version(root)
    print(f"Building NailQue Windows artifacts for version {version}")

    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=root)
    run([sys.executable, "build_executable.py"], cwd=root)

    exe_path = dist_dir / "NailQue.exe"
    if not exe_path.exists():
        raise RuntimeError(f"Expected executable not found: {exe_path}")

    standalone_zip = build_standalone_zip(exe_path, out_dir, version, work_dir)
    print(f"Standalone artifact: {standalone_zip}")

    iscc_path = locate_iscc()
    iss_path = write_iss_script(exe_path, out_dir, work_dir, version)
    run([str(iscc_path), str(iss_path)], cwd=root)

    versioned_setup = out_dir / f"NailQue-Setup-{safe_version_for_filename(version)}.exe"
    stable_setup = out_dir / "NailQue-Setup.exe"
    if versioned_setup.exists():
        shutil.copy2(versioned_setup, stable_setup)
        print(f"Installer artifact: {versioned_setup}")
        print(f"Latest alias:       {stable_setup}")
    else:
        print("Inno Setup completed but expected installer filename was not found.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # pragma: no cover
        print(f"ERROR: {error}")
        raise SystemExit(1)
