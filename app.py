from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "torrentguard.db"
ALLOWED_EXTENSION = ".torrent"

app = Flask(__name__)
# No upload size limit: MAX_CONTENT_LENGTH is explicitly unset (None).
app.config["MAX_CONTENT_LENGTH"] = None
app.config["SECRET_KEY"] = os.environ.get("TORRENTGUARD_SECRET", "change-this-for-production")
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SUSPICIOUS_EXTENSIONS = {
    ".exe", ".dll", ".scr", ".bat", ".cmd", ".com", ".ps1", ".vbs",
    ".js", ".jse", ".wsf", ".hta", ".msi", ".jar", ".sh", ".app",
    ".dmg", ".iso", ".lnk"
}
DOUBLE_EXTENSION_HINTS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt", ".xlsx"}


class BencodeError(ValueError):
    """Raised when a torrent file contains invalid or unsupported bencode."""


def decode_bencode(data: bytes, max_depth: int = 80) -> Any:
    """Decode bencode safely without evaluating any content."""
    index = 0

    def parse(depth: int = 0) -> Any:
        nonlocal index
        if depth > max_depth or index >= len(data):
            raise BencodeError("Malformed or excessively nested bencode data.")

        token = data[index:index + 1]
        if token == b"i":
            index += 1
            end = data.find(b"e", index)
            if end < 0:
                raise BencodeError("Invalid integer value.")
            raw = data[index:end]
            if not raw or (raw.startswith(b"-") and not raw[1:].isdigit()) or (
                not raw.startswith(b"-") and not raw.isdigit()
            ):
                raise BencodeError("Invalid integer value.")
            index = end + 1
            try:
                return int(raw)
            except ValueError as exc:
                raise BencodeError("Invalid integer value.") from exc

        if token == b"l":
            index += 1
            result = []
            while index < len(data) and data[index:index + 1] != b"e":
                result.append(parse(depth + 1))
            if index >= len(data):
                raise BencodeError("Unterminated list.")
            index += 1
            return result

        if token == b"d":
            index += 1
            result = {}
            while index < len(data) and data[index:index + 1] != b"e":
                key = parse(depth + 1)
                if not isinstance(key, bytes):
                    raise BencodeError("Dictionary keys must be byte strings.")
                value = parse(depth + 1)
                result[key] = value
            if index >= len(data):
                raise BencodeError("Unterminated dictionary.")
            index += 1
            return result

        if token.isdigit():
            colon = data.find(b":", index)
            if colon < 0:
                raise BencodeError("Invalid byte-string length.")
            raw_length = data[index:colon]
            if not raw_length.isdigit() or (len(raw_length) > 1 and raw_length.startswith(b"0")):
                raise BencodeError("Invalid byte-string length.")
            length = int(raw_length)
            start = colon + 1
            end = start + length
            if end > len(data):
                raise BencodeError("Byte string extends beyond the file.")
            index = end
            return data[start:end]

        raise BencodeError("Unrecognized bencode token.")

    decoded = parse()
    if index != len(data):
        raise BencodeError("Unexpected data after the torrent metadata.")
    return decoded


def text_value(value: Any, default: str = "") -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return default


def safe_file_path(value: str) -> str:
    return value.replace("\\\\", "/").strip()


def analyze_torrent(filename: str, raw: bytes) -> dict[str, Any]:
    root = decode_bencode(raw)
    if not isinstance(root, dict):
        raise BencodeError("The torrent root must be a dictionary.")

    info = root.get(b"info")
    if not isinstance(info, dict):
        raise BencodeError("The torrent file does not contain a valid info dictionary.")

    name = text_value(info.get(b"name.utf-8") or info.get(b"name"), "Unknown torrent")
    files: list[dict[str, Any]] = []
    total_size = 0

    if isinstance(info.get(b"files"), list):
        for item in info[b"files"]:
            if not isinstance(item, dict):
                continue
            raw_path = item.get(b"path.utf-8") or item.get(b"path") or []
            parts = [text_value(part) for part in raw_path] if isinstance(raw_path, list) else []
            path = safe_file_path("/".join(parts))
            length = item.get(b"length", 0)
            size = length if isinstance(length, int) and length >= 0 else 0
            total_size += size
            files.append({"path": path or "(unnamed file)", "size": size})
    else:
        length = info.get(b"length", 0)
        size = length if isinstance(length, int) and length >= 0 else 0
        total_size = size
        files.append({"path": name, "size": size})

    trackers = []
    announce = root.get(b"announce")
    if isinstance(announce, bytes):
        trackers.append(text_value(announce))
    announce_list = root.get(b"announce-list")
    if isinstance(announce_list, list):
        for tier in announce_list:
            if isinstance(tier, list):
                for tracker in tier:
                    if isinstance(tracker, bytes):
                        trackers.append(text_value(tracker))
            elif isinstance(tier, bytes):
                trackers.append(text_value(tier))
    trackers = list(dict.fromkeys(trackers))

    flags: list[dict[str, str]] = []
    score = 0

    if not files:
        flags.append({"level": "warning", "title": "No file entries found", "detail": "The metadata does not list any content files."})
        score += 10

    for item in files:
        path = item["path"]
        suffix = Path(path.lower()).suffix
        parts = [part for part in path.replace("\\\\", "/").split("/") if part]
        if suffix in SUSPICIOUS_EXTENSIONS:
            flags.append({
                "level": "high",
                "title": f"Executable or script file: {path}",
                "detail": "This file type can run code. It is a review signal, not proof of malware."
            })
            score += 25
        if len(parts) >= 2 and Path(parts[-2].lower()).suffix in DOUBLE_EXTENSION_HINTS and suffix in SUSPICIOUS_EXTENSIONS:
            flags.append({
                "level": "high",
                "title": f"Possible misleading double extension: {path}",
                "detail": "A document or image-like name is followed by an executable extension."
            })
            score += 15
        if path.startswith("/") or ".." in parts:
            flags.append({
                "level": "medium",
                "title": f"Unusual file path: {path}",
                "detail": "The path contains an absolute-path or parent-directory pattern."
            })
            score += 15

    if any(tracker.lower().startswith("http://") for tracker in trackers):
        flags.append({
            "level": "low",
            "title": "Unencrypted HTTP tracker",
            "detail": "At least one tracker URL uses HTTP. This is not itself evidence of malware."
        })
        score += 5

    if not trackers:
        flags.append({
            "level": "info",
            "title": "No tracker URL listed",
            "detail": "This may be intentional for a magnet-style or decentralized workflow."
        })

    if len(files) > 5000:
        flags.append({
            "level": "medium",
            "title": "Large file list",
            "detail": f"The metadata lists {len(files):,} files; inspect the list carefully."
        })
        score += 10

    score = min(score, 100)
    risk = "High" if score >= 50 else "Medium" if score >= 20 else "Low"
    if not flags:
        flags.append({
            "level": "info",
            "title": "No obvious metadata indicators found",
            "detail": "This limited static check did not find configured warning patterns. It is not a malware clearance."
        })

    return {
        "filename": filename,
        "torrent_name": name,
        "file_count": len(files),
        "total_size": total_size,
        "trackers": trackers,
        "files": files[:1000],
        "files_truncated": len(files) > 1000,
        "risk_score": score,
        "risk_level": risk,
        "flags": flags,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope_note": "This report analyzes only the uploaded .torrent metadata. It does not download or scan the content files."
    }


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with db_connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                torrent_name TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                file_count INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                scanned_at TEXT NOT NULL,
                report_json TEXT NOT NULL
            )
        """)


init_db()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/history")
def history():
    with db_connect() as connection:
        rows = connection.execute(
            "SELECT id, filename, torrent_name, risk_level, risk_score, file_count, sha256, scanned_at "
            "FROM scans ORDER BY id DESC LIMIT 10"
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/report/<int:scan_id>")
def get_report(scan_id: int):
    with db_connect() as connection:
        row = connection.execute("SELECT report_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Scan report not found."}), 404
    return jsonify(json.loads(row["report_json"]))


@app.post("/api/scan")
def scan():
    uploaded = request.files.get("torrent_file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Choose a .torrent file first."}), 400

    filename = Path(uploaded.filename).name
    if Path(filename).suffix.lower() != ALLOWED_EXTENSION:
        return jsonify({"error": "Only .torrent metadata files are accepted."}), 400

    raw = uploaded.stream.read()
    if not raw:
        return jsonify({"error": "The uploaded file is empty."}), 400

    try:
        report = analyze_torrent(filename, raw)
    except BencodeError as exc:
        return jsonify({"error": f"Could not read this torrent file: {exc}"}), 400
    except Exception:
        app.logger.exception("Unexpected error while analyzing torrent metadata")
        return jsonify({"error": "An unexpected error occurred while analyzing this file."}), 500

    with db_connect() as connection:
        cursor = connection.execute(
            "INSERT INTO scans (filename, torrent_name, risk_level, risk_score, file_count, sha256, scanned_at, report_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report["filename"], report["torrent_name"], report["risk_level"],
                report["risk_score"], report["file_count"], report["sha256"],
                report["scanned_at"], json.dumps(report)
            )
        )
        report["scan_id"] = cursor.lastrowid

    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
