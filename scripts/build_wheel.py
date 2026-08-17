#!/usr/bin/env python3
"""Build a minimal pure-Python wheel using only the standard library."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import zipfile
from pathlib import Path

NAME = "heritagegate"
VERSION = "0.5.1"
TAG = "py3-none-any"
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WHEEL_PATH = DIST / f"{NAME}-{VERSION}-{TAG}.whl"
DIST_INFO = f"{NAME}-{VERSION}.dist-info"


def digest(data: bytes) -> str:
    value = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return "sha256=" + value.decode("ascii")


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    for old_wheel in DIST.glob(f"{NAME}-*.whl"):
        old_wheel.unlink()
    files: dict[str, bytes] = {}
    package_dir = ROOT / "src" / NAME
    for path in sorted(package_dir.glob("*.py")):
        files[f"{NAME}/{path.name}"] = path.read_bytes()

    metadata = f"""Metadata-Version: 2.3
Name: {NAME}
Version: {VERSION}
Summary: A stage-gated, rights-aware workflow with privacy-aware real-pilot enrollment, reproducible statistics, and GitHub, Zenodo, and SoftwareX release preparation for AI-assisted intangible cultural heritage projects.
License-Expression: Apache-2.0
Requires-Python: >=3.10
Classifier: Development Status :: 4 - Beta
Classifier: Intended Audience :: Science/Research
Classifier: License :: OSI Approved :: Apache Software License
Classifier: Programming Language :: Python :: 3

""".encode("utf-8")
    files[f"{DIST_INFO}/METADATA"] = metadata
    files[f"{DIST_INFO}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        "Generator: HeritageGate standard-library wheel builder\n"
        "Root-Is-Purelib: true\n"
        f"Tag: {TAG}\n\n"
    ).encode("utf-8")
    files[f"{DIST_INFO}/entry_points.txt"] = (
        "[console_scripts]\nheritagegate = heritagegate.cli:main\n"
    ).encode("utf-8")
    files[f"{DIST_INFO}/top_level.txt"] = b"heritagegate\n"
    files[f"{DIST_INFO}/licenses/LICENSE"] = (ROOT / "LICENSE").read_bytes()

    record_rows: list[list[str]] = []
    for archive_name, data in files.items():
        record_rows.append([archive_name, digest(data), str(len(data))])
    record_name = f"{DIST_INFO}/RECORD"
    record_rows.append([record_name, "", ""])
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(record_rows)
    files[record_name] = buffer.getvalue().encode("utf-8")

    with zipfile.ZipFile(WHEEL_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for archive_name, data in sorted(files.items()):
            info = zipfile.ZipInfo(archive_name, date_time=(2026, 7, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    print(WHEEL_PATH)


if __name__ == "__main__":
    main()
