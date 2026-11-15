"""Synchronized terminal lyrics player with mpv/ffplay audio and yt-dlp streaming."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from lrc_client import LyricLine

YELLOW = "\033[93m"
DIM = "\033[90m"
RESET = "\033[0m"


def resolve_stream_url(query: str, timeout: float = 15.0) -> str | None:
    """Resolve a direct audio stream URL for `query` using yt-dlp."""
    if not shutil.which("yt-dlp"):
        return None
    try:
        proc = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "-f",
                "bestaudio",
                "-g",
                f"ytsearch1:{query}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        url = line.strip()
        if url:
            return url
    return None


class _MpvPlayer:
    """Manages an mpv subprocess (optionally fed by yt-dlp) with IPC time-pos sync."""

    def __init__(self, source: str) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="terminal_lyrics_")
        self._socket_path = Path(self._tmpdir.name) / "mpv.sock"
        self._ytdlp_proc: subprocess.Popen[bytes] | None = None

        mpv_cmd = [
            "mpv",
            "--no-video",
            "--no-terminal",
            "--msg-level=all=error",
            f"--input-ipc-server={self._socket_path}",
        ]

        if source.startswith("ytdl://"):
            yt_query = source.removeprefix("ytdl://")
            self._ytdlp_proc = subprocess.Popen(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--quiet",
                    "-f",
                    "bestaudio",
                    "-o",
                    "-",
                    yt_query,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            mpv_cmd.append("-")
            self._proc = subprocess.Popen(
                mpv_cmd,
                stdin=self._ytdlp_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if self._ytdlp_proc.stdout is not None:
                self._ytdlp_proc.stdout.close()
        else:
            mpv_cmd.append(source)
            self._proc = subprocess.Popen(
                mpv_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        self._sock: socket.socket | None = None

    def _ensure_socket(self, timeout: float = 20.0) -> bool:
        if self._sock is not None:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                return False
            if self._socket_path.exists():
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(1.0)
                    sock.connect(str(self._socket_path))
                    self._sock = sock
                    return True
                except OSError:
                    time.sleep(0.05)
            else:
                time.sleep(0.05)
        return False

    def get_time_pos(self) -> float | None:
        """Query current playback position in seconds from mpv IPC."""
        if self._sock is None and not self._ensure_socket():
            return None
        assert self._sock is not None
        try:
            self._sock.sendall(b'{"command": ["get_property", "time-pos"]}\n')
            raw = self._sock.recv(4096).decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                payload = json.loads(line)
                if payload.get("error") == "success" and isinstance(
                    payload.get("data"), (int, float)
                ):
                    return float(payload["data"])
        except (OSError, ValueError):
            return None
        return None

    def wait_until_playing(self, timeout: float = 35.0) -> bool:
        """Wait until mpv starts outputting audio and reports a valid time-pos."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                return False
            if self._ytdlp_proc is not None and self._ytdlp_proc.poll() not in (None, 0):
                return False
            pos = self.get_time_pos()
            if pos is not None and pos >= 0.0:
                return True
            time.sleep(0.05)
        return False

    def read_stderr(self) -> str:
        """Read any error output if mpv or yt-dlp has exited."""
        messages: list[str] = []
        if self._ytdlp_proc is not None and self._ytdlp_proc.stderr is not None:
            if self._ytdlp_proc.poll() is not None:
                err = self._ytdlp_proc.stderr.read().decode("utf-8", errors="ignore").strip()
                if err:
                    messages.append(err)
        if self._proc.stderr is not None and self._proc.poll() is not None:
            err = self._proc.stderr.read().decode("utf-8", errors="ignore").strip()
            if err:
                messages.append(err)
        return "\n".join(messages).strip()

    def wait(self) -> None:
        self._proc.wait()

    def poll(self) -> int | None:
        return self._proc.poll()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        for proc in (self._proc, self._ytdlp_proc):
            if proc is None:
                continue
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

        if self._proc.stderr is not None:
            self._proc.stderr.close()
        if self._ytdlp_proc is not None and self._ytdlp_proc.stderr is not None:
            self._ytdlp_proc.stderr.close()
        self._tmpdir.cleanup()


def _type_line(text: str, max_duration: float) -> None:
    """Print `text` with a yellow typewriter effect bounded by `max_duration`."""
    if not text:
        print()
        return

    char_count = len(text)
    usable_window = max(0.2, max_duration * 0.75)
    char_delay = min(0.065, max(0.015, usable_window / char_count))

    sys.stdout.write(YELLOW)
    sys.stdout.flush()
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(char_delay)
    sys.stdout.write(f"{RESET}\n")
    sys.stdout.flush()


def _wait_for_timestamp(
    target_ts: float,
    start_time: float,
    mpv_player: _MpvPlayer | None,
) -> bool:
    """Wait until playback reaches `target_ts`. Returns False if audio ended early."""
    while True:
        if mpv_player is not None:
            if mpv_player.poll() is not None:
                return False
            pos = mpv_player.get_time_pos()
            if pos is not None:
                remaining = target_ts - pos
                if remaining <= 0:
                    return True
                time.sleep(min(0.05, remaining))
                continue

        remaining = (start_time + target_ts) - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(0.05, remaining))


def play_lyrics(
    lyrics: list[LyricLine],
    audio_source: str | Path | None = None,
) -> None:
    """Display `lyrics` with a typewriter effect synchronized to `audio_source`."""
    if not lyrics:
        print("No hay líneas sincronizadas para reproducir.")
        return

    mpv_player: _MpvPlayer | None = None
    ffplay_proc: subprocess.Popen[bytes] | None = None

    if audio_source is not None:
        source_str = str(audio_source)
        if isinstance(audio_source, Path) and not audio_source.is_file():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {audio_source}")

        if shutil.which("mpv"):
            mpv_player = _MpvPlayer(source_str)
            if not mpv_player.wait_until_playing():
                err = mpv_player.read_stderr()
                mpv_player.close()
                mpv_player = None
                detail = f" ({err.splitlines()[-1]})" if err else ""
                print(
                    f"{DIM}⚠️  No se pudo iniciar el audio con mpv{detail}; "
                    f"se reproducirá solo la letra.{RESET}\n"
                )
        elif shutil.which("ffplay"):
            ffplay_proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", source_str],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            print(
                f"{DIM}⚠️  No se encontró 'mpv' ni 'ffplay'; "
                f"se reproducirá solo la letra.{RESET}\n"
            )

    if lyrics[0].timestamp > 3.0:
        mins, secs = divmod(int(lyrics[0].timestamp), 60)
        print(f"{DIM}♪ Intro... (primera línea en {mins:02d}:{secs:02d}){RESET}")

    start_time = time.monotonic()
    try:
        for idx, line in enumerate(lyrics):
            if not _wait_for_timestamp(line.timestamp, start_time, mpv_player):
                break
            if idx + 1 < len(lyrics):
                gap = max(0.4, lyrics[idx + 1].timestamp - line.timestamp)
            else:
                gap = 3.0
            _type_line(line.text, max_duration=gap)

        if mpv_player is not None:
            mpv_player.wait()
        elif ffplay_proc is not None:
            ffplay_proc.wait()
    except KeyboardInterrupt:
        print(f"{RESET}\n⏹ Reproducción detenida.")
    finally:
        if mpv_player is not None:
            mpv_player.close()
        if ffplay_proc is not None and ffplay_proc.poll() is None:
            ffplay_proc.terminate()
            try:
                ffplay_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                ffplay_proc.kill()
