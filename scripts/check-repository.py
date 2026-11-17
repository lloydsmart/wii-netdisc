"""Validate the research repository without touching its index or history."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "research/historical/wii-network-launcher-development.json"
LICENSE_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
BLOCKED_SUFFIXES = {
    ".iso", ".wbfs", ".wad", ".rvz", ".wia", ".chd", ".dol", ".elf",
    ".nand", ".key", ".pem", ".p12", ".pfx",
}


def main():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True,
    )
    names = sorted(set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""})
    errors = []
    for name in names:
        path = ROOT / name
        if (
            name == ARCHIVE
            or path.suffix.lower() in BLOCKED_SUFFIXES
            or path.name.lower() in {"nand.bin", "keys.bin", ".env"}
            or (path.name.startswith(".env.") and path.name != ".env.example")
        ):
            errors.append(f"{name}: local/private payload must not be included")
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            errors.append(f"{name}: symlink or path outside repository")
            continue
        if not path.is_file():
            errors.append(f"{name}: missing file or unsupported directory entry")
            continue
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"{name}: expected UTF-8 text in the research skeleton")
            continue
        if data.startswith(b"\xef\xbb\xbf") or b"\r" in data:
            errors.append(f"{name}: use UTF-8 without BOM and LF line endings")
        if data and not data.endswith(b"\n"):
            errors.append(f"{name}: missing final newline")
        if any(line.rstrip(" \t") != line for line in text.splitlines()):
            errors.append(f"{name}: trailing whitespace")
        if path.suffix == ".json":
            try:
                json.loads(text)
            except ValueError:
                errors.append(f"{name}: invalid JSON")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^\s)]+)\)", text):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                linked = (path.parent / unquote(parsed.path)).resolve()
                if not linked.is_relative_to(ROOT) or not linked.exists():
                    errors.append(f"{name}: broken/outside local link: {target}")
    licence = ROOT / "LICENSE"
    if not licence.is_file() or hashlib.sha256(licence.read_bytes()).hexdigest() != LICENSE_SHA256:
        errors.append("LICENSE: expected the unmodified GPL version 3 text")
    readme = ROOT / "README.md"
    if not readme.is_file() or "SPDX-License-Identifier: GPL-3.0-only" not in readme.read_text():
        errors.append("README.md: missing explicit GPL-3.0-only declaration")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Repository checks passed for {len(names)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
