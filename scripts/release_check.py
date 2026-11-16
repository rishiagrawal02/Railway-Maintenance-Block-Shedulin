"""Release hygiene checks over Git's index; never print secret values."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

GOLDENS = {
    f"{kind}_n{n}_s{seed}" for kind in ("simplified", "extended") for n, seed in ((25, 1), (50, 42))
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(
        r"""(?i)\b(?:api_key|access_token|client_secret|password)\s*[:=]\s*["']([A-Za-z0-9_+/=-]{20,})["']"""
    ),
)
PLACEHOLDERS = ("example", "placeholder", "your_", "replace", "dummy", "changeme")


def indexed_files(root):
    """Read staged blobs, so even staged-only sensitive content is inspected."""
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root).split(b"\0")
    records = []
    for entry in entries:
        if not entry:
            continue
        info, name = entry.split(b"\t", 1)
        mode, oid, stage = info.split()
        if stage != b"0":
            raise ValueError("Resolve merge conflicts before release checks.")
        records.append((name.decode("utf-8"), oid, mode))
    if not records:
        raise ValueError("No tracked files found.")
    raw = subprocess.check_output(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=b"\n".join(oid for _, oid, _ in records) + b"\n",
    )
    files, position = {}, 0
    for name, _, mode in records:
        end = raw.index(b"\n", position)
        size = int(raw[position:end].split()[-1])
        position = end + 1
        files[name] = raw[position : position + size]
        position += size + 1
        if mode == b"120000":
            raise ValueError(f"Tracked symlink requires review: {name}")
    return files


def check_files(files):
    errors = []
    for name in files:
        if name.startswith(("results/", "data/generated/")):
            errors.append(f"Generated output is tracked: {name}")
        if any(
            part in {".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
            for part in Path(name).parts
        ):
            errors.append(f"Environment or cache file is tracked: {name}")
        if len(files[name]) > 5 * 1024 * 1024:
            errors.append(f"Tracked file exceeds the 5 MB release cap: {name}")
        if Path(name).name in (".env", "secrets.toml", "id_rsa", "id_ed25519"):
            errors.append(f"Sensitive filename is tracked: {name}")
    try:
        threshold = json.loads(files["config/threshold.json"])
        version = threshold.get("version")
        if type(version) is not int or version < 1:
            errors.append("Threshold version must be an integer >= 1, not a placeholder.")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("Missing or invalid config/threshold.json.")
    try:
        hashes = json.loads(files["tests/data/golden_hashes.json"])
        if (
            not isinstance(hashes, dict)
            or not GOLDENS <= hashes.keys()
            or any(
                not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                for v in hashes.values()
            )
        ):
            errors.append("Golden hashes must include all four named SHA-256 fixtures.")
    except (KeyError, ValueError, TypeError):
        errors.append("Missing or invalid golden hashes.")
    for name, content in files.items():
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if match and not any(p in match.group().lower() for p in PLACEHOLDERS):
                    errors.append(f"Potential credential: {name}:{number} (value redacted)")
                    break
        if not name.endswith(".md"):
            continue
        # Ignore fenced code, which contains example links rather than documentation links.
        text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)
        targets = re.findall(r"!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text)
        targets += re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(\S+)", text)
        for target in targets:
            target = target.strip("<>")
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            path = unquote(url.path).replace("\\", "/")
            import posixpath

            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
            if resolved.startswith("../") or path.startswith("/"):
                errors.append(f"Nonportable documentation link: {name} -> {target}")
            elif resolved not in files and not any(
                f.startswith(resolved.rstrip("/") + "/") for f in files
            ):
                errors.append(f"Broken relative link: {name} -> {target}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        files = indexed_files(args.root)
        errors = check_files(files)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Release check could not inspect the index: {exc}")
        return 1
    for error in errors:
        print("FAIL:", error)
    if errors:
        return 1
    print(
        f"PASS: {len(files)} indexed files; threshold, golden hashes, output hygiene, "
        "credential patterns and relative documentation links checked."
    )
    print("This is a hygiene check, not certification of independent reproduction or deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
