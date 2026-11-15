"""Client for searching synced lyrics on LRCLIB and parsing .lrc files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import requests

LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
USER_AGENT = "TerminalLyrics/1.0 (https://github.com/terminal-lyrics)"

_TIMESTAMP_PATTERN = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


@dataclass(frozen=True)
class TrackResult:
    """Represents a song result returned by LRCLIB."""

    track_id: int
    track_name: str
    artist_name: str
    album_name: str
    duration: float
    synced_lyrics: str


@dataclass(frozen=True)
class LyricLine:
    """A single timestamped lyric line."""

    timestamp: float
    text: str


def search_songs(query: str, timeout: float = 10.0) -> list[TrackResult]:
    """Search LRCLIB for songs matching `query` that include synced lyrics."""
    response = requests.get(
        LRCLIB_SEARCH_URL,
        params={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()

    results: list[TrackResult] = []
    for item in response.json():
        synced = item.get("syncedLyrics")
        if not synced or not synced.strip():
            continue
        results.append(
            TrackResult(
                track_id=int(item.get("id", 0)),
                track_name=str(item.get("trackName") or "Desconocido"),
                artist_name=str(item.get("artistName") or "Desconocido"),
                album_name=str(item.get("albumName") or ""),
                duration=float(item.get("duration") or 0.0),
                synced_lyrics=synced,
            )
        )
    return results


def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip()
    return cleaned or "track"


def save_lrc(track: TrackResult, output_dir: Path = Path("lyrics")) -> Path:
    """Save synced lyrics of `track` to an .lrc file and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(f"{track.track_name} - {track.artist_name}") + ".lrc"
    file_path = output_dir / filename
    file_path.write_text(track.synced_lyrics, encoding="utf-8")
    return file_path


def parse_lrc(lrc_content: str) -> list[LyricLine]:
    """Parse LRC text into a sorted list of `LyricLine` entries."""
    lines: list[LyricLine] = []
    for raw_line in lrc_content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        matches = list(_TIMESTAMP_PATTERN.finditer(stripped))
        if not matches:
            continue
        text = _TIMESTAMP_PATTERN.sub("", stripped).strip()
        for match in matches:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            lines.append(LyricLine(timestamp=minutes * 60 + seconds, text=text))
    lines.sort(key=lambda item: item.timestamp)
    return lines


def load_lrc(file_path: Path) -> list[LyricLine]:
    """Load and parse an .lrc file from disk."""
    content = file_path.read_text(encoding="utf-8")
    return parse_lrc(content)
