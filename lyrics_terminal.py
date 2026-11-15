"""CLI entry point for searching and playing synchronized lyrics in the terminal."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import requests

from lrc_client import TrackResult, load_lrc, parse_lrc, save_lrc, search_songs
from player import play_lyrics, resolve_stream_url

CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[90m"
RESET = "\033[0m"


def _select_track(results: list[TrackResult]) -> TrackResult | None:
    """Display search results and prompt the user to pick one."""
    print(f"\n{CYAN}Se encontraron {len(results)} resultados:{RESET}\n")
    for index, track in enumerate(results, start=1):
        print(f"  {GREEN}{index}.{RESET} {track.track_name} – {DIM}{track.artist_name}{RESET}")

    print()
    while True:
        choice = input(f"{CYAN}Elige un número (o 'q' para salir): {RESET}").strip()
        if choice.lower() == "q":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(results):
                return results[idx - 1]
        print(f"{RED}Opción inválida. Ingresa un número del 1 al {len(results)} o 'q'.{RESET}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Busca canciones y reproduce su audio y letra sincronizada en la terminal."
    )
    parser.add_argument(
        "-q",
        "--query",
        help="Nombre de la canción y/o artista para buscar directamente.",
    )
    parser.add_argument(
        "-a",
        "--audio",
        type=Path,
        help="Ruta a un archivo de audio local (.mp3, .flac, .wav) para reproducir sincronizado.",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Reproducir solo la letra sin buscar ni reproducir audio.",
    )
    parser.add_argument(
        "--lrc",
        type=Path,
        help="Ruta a un archivo .lrc local para reproducir sin buscar en la API.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="No guardar el archivo .lrc descargado en la carpeta lyrics/.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.lrc is not None:
        if not args.lrc.is_file():
            print(f"{RED}Archivo .lrc no encontrado: {args.lrc}{RESET}")
            return 1
        lyrics = load_lrc(args.lrc)
        audio_source = None if args.no_audio else args.audio
        print(f"\n{GREEN}▶ Reproduciendo letra...{RESET}\n")
        play_lyrics(lyrics, audio_source=audio_source)
        return 0

    query = args.query
    if not query:
        try:
            query = input(
                f"{CYAN}🔍 Busca una canción (nombre y/o artista): {RESET}"
            ).strip()
        except EOFError:
            return 0

    if not query:
        print(f"{RED}Debes ingresar una búsqueda.{RESET}")
        return 1

    try:
        results = search_songs(query)
    except requests.RequestException as exc:
        print(f"{RED}Error al conectar con LRCLIB: {exc}{RESET}")
        return 1

    if not results:
        print(f"{RED}No se encontraron letras sincronizadas para '{query}'.{RESET}")
        return 0

    selected = _select_track(results)
    if selected is None:
        return 0

    if not args.no_save:
        saved_path = save_lrc(selected)
        print(f"{GREEN}✅ Letra sincronizada guardada en:{RESET} {saved_path}")

    audio_source: str | Path | None = None
    if not args.no_audio:
        if args.audio is not None:
            audio_source = args.audio
        elif shutil.which("mpv") and shutil.which("yt-dlp"):
            print(f"{CYAN}🎵 Buscando audio...{RESET}")
            audio_source = f"ytdl://ytsearch1:{selected.track_name} {selected.artist_name} audio"
        else:
            print(f"{CYAN}🎵 Buscando audio...{RESET}")
            audio_source = resolve_stream_url(
                f"{selected.track_name} {selected.artist_name} audio"
            )
            if audio_source is None:
                print(f"{DIM}⚠️  No se pudo obtener el audio; se reproducirá solo la letra.{RESET}")

    lyrics = parse_lrc(selected.synced_lyrics)
    if audio_source is not None:
        print(f"\n{GREEN}▶ Reproduciendo canción y letra...{RESET}\n")
    else:
        print(f"\n{GREEN}▶ Reproduciendo letra...{RESET}\n")
    play_lyrics(lyrics, audio_source=audio_source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
