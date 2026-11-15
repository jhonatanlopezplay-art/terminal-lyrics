# Terminal Lyrics

Busca canciones en la API pública de [LRCLIB](https://lrclib.net/), descarga su archivo `.lrc` y reproduce **el audio de la canción** (vía `yt-dlp` + `mpv`) junto con la **letra sincronizada** en la terminal con efecto máquina de escribir.

## Requisitos

- Python 3.10+
- `requests` (`pip install -r requirements.txt`)
- Para reproducir audio automáticamente: `yt-dlp` y `mpv` (o `ffplay` para archivos locales)

## Uso

Modo interactivo (busca, descarga `.lrc`, obtiene el audio y reproduce todo sincronizado):

```bash
python3 lyrics_terminal.py
```

Buscar directamente desde la línea de comandos:

```bash
python3 lyrics_terminal.py -q "emmanuel cortes amor"
```

Reproducir solo la letra sin audio:

```bash
python3 lyrics_terminal.py -q "emmanuel cortes amor" --no-audio
```

Reproducir letra sincronizada junto con un archivo de audio local:

```bash
python3 lyrics_terminal.py -q "emmanuel cortes amor" -a ruta/a/cancion.mp3
```

Reproducir un archivo `.lrc` guardado previamente:

```bash
python3 lyrics_terminal.py --lrc "lyrics/AMOR - Emmanuel Cortes.lrc"
```
