$ErrorActionPreference = "Stop"

$ruff = if (Test-Path ".\.venv\Scripts\ruff.exe") { ".\.venv\Scripts\ruff.exe" } else { "ruff" }
$pytest = if (Test-Path ".\.venv\Scripts\pytest.exe") { ".\.venv\Scripts\pytest.exe" } else { "pytest" }

Write-Host "Running ruff check..."
& $ruff check .

Write-Host "Running pytest (not slow)..."
& $pytest -m "not slow"
