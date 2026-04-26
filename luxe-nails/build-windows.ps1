Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
python ".\installers\windows\build-windows-installer.py"
