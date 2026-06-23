# yt-dlp Music-Making Cookbook

> yt-dlp 2026.03.17 · ffmpeg 8.1 · macOS  
> **Legal notice:** Download only content you have rights to use. Sample clearance,
> licensing, and fair-use determinations are entirely your responsibility.

---

## Setup

```bash
# Verify installation
yt-dlp --version    # 2026.03.17
ffmpeg -version     # 8.1

# Update
brew upgrade yt-dlp
```

---

## Best-Quality Audio Extraction

### MP3 (best quality, widest compatibility)
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --embed-metadata --embed-thumbnail \
  -o "%(title)s.%(ext)s" \
  "URL"
```

### FLAC (lossless — best for sampling)
```bash
yt-dlp -x --audio-format flac \
  --embed-metadata \
  -o "%(artist)s - %(title)s.%(ext)s" \
  "URL"
```

### WAV (uncompressed — immediate DAW-ready)
```bash
yt-dlp -x --audio-format wav \
  -o "%(title)s.%(ext)s" \
  "URL"
```

### Best available (let yt-dlp pick; no transcode)
```bash
yt-dlp -x --audio-format best \
  -o "%(title)s.%(ext)s" \
  "URL"
```

**Flag cheatsheet:**
| Flag | Meaning |
|------|---------|
| `-x` | Extract audio (discard video) |
| `--audio-format mp3/flac/wav/best` | Output format |
| `--audio-quality 0` | VBR best (0=best, 9=worst) for mp3; ignored for lossless |
| `--embed-metadata` | Write title/artist/album tags into file |
| `--embed-thumbnail` | Embed cover art |

---

## Single Track Download

```bash
yt-dlp -x --audio-format flac \
  --embed-metadata --embed-thumbnail \
  -o "~/Music/Samples/%(uploader)s/%(title)s.%(ext)s" \
  "https://example.com/watch?v=XXXX"
```

---

## Playlist Handling

### Entire playlist — one file per track
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --embed-metadata --embed-thumbnail \
  --yes-playlist \
  -o "%(playlist_title)s/%(playlist_index)02d - %(title)s.%(ext)s" \
  "PLAYLIST_URL"
```

### Single track from a playlist URL (ignore rest)
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --no-playlist \
  "PLAYLIST_URL_WITH_INDEX"
```

### Download tracks N through M only
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --playlist-items 3-7 \
  -o "%(playlist_index)02d - %(title)s.%(ext)s" \
  "PLAYLIST_URL"
```

---

## Time-Range Clips (for sampling specific sections)

Requires ffmpeg. `--download-sections` accepts `*START-END` syntax.

```bash
# Grab 0:30–1:15 only
yt-dlp -x --audio-format flac \
  --download-sections "*00:00:30-00:01:15" \
  -o "%(title)s_clip.%(ext)s" \
  "URL"

# Multiple clips in one pass
yt-dlp -x --audio-format flac \
  --download-sections "*00:00:30-00:01:00" \
  --download-sections "*00:02:45-00:03:30" \
  -o "%(title)s_%(section_start)s.%(ext)s" \
  "URL"

# From 2-minute mark to end
yt-dlp -x --audio-format flac \
  --download-sections "*00:02:00-inf" \
  -o "%(title)s_tail.%(ext)s" \
  "URL"
```

---

## Metadata Embedding

```bash
# Write all available metadata + lyrics (if available)
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --embed-metadata \
  --embed-thumbnail \
  --write-info-json \
  -o "%(title)s.%(ext)s" \
  "URL"

# Add custom output template with metadata fields
yt-dlp -x --audio-format mp3 \
  -o "%(upload_date>%Y)s/%(uploader)s/%(title)s.%(ext)s" \
  "URL"
```

---

## Batch Download from a URL File

```bash
# urls.txt — one URL per line; lines starting with # are ignored
yt-dlp -x --audio-format flac \
  --embed-metadata \
  -o "%(title)s.%(ext)s" \
  --batch-file urls.txt

# With concurrency (faster for large batches)
yt-dlp -x --audio-format flac \
  --concurrent-fragments 4 \
  -o "%(title)s.%(ext)s" \
  --batch-file urls.txt
```

`urls.txt` example:
```
# Drums
https://example.com/watch?v=AAAA
# Bass
https://example.com/watch?v=BBBB
```

---

## Output Templates

| Template token | Expands to |
|---|---|
| `%(title)s` | Track title |
| `%(uploader)s` | Channel / artist name |
| `%(upload_date)s` | YYYYMMDD |
| `%(playlist_title)s` | Playlist name |
| `%(playlist_index)02d` | Zero-padded track number |
| `%(duration_string)s` | HH:MM:SS |
| `%(ext)s` | File extension |

---

## Format Inspection

```bash
# List all available formats
yt-dlp -F "URL"

# Download a specific format by ID
yt-dlp -f 251 "URL"           # e.g. webm opus 160kbps
yt-dlp -f bestaudio "URL"     # best audio stream, no video

# Print what would be downloaded (no download)
yt-dlp --simulate --print "%(title)s | %(duration_string)s | %(filesize_approx)s" "URL"
```

---

## Skip Already-Downloaded Files

```bash
# Write a download archive — skip re-downloading
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  --download-archive ~/Music/Samples/downloaded.txt \
  --batch-file urls.txt
```

---

## Useful Flags Reference

| Flag | Use case |
|---|---|
| `--cookies-from-browser chrome` | Access age-gated or account-required content |
| `--sleep-interval 2` | Polite delay between downloads |
| `--rate-limit 2M` | Cap bandwidth |
| `--retries 3` | Retry on failure |
| `--ignore-errors` | Keep going if one URL in a batch fails |
| `--verbose` | Debug failing downloads |
| `-q --progress` | Quiet except progress bar |

---

## Legal Note

yt-dlp is a tool. What you do with it is on you.

- Download only content you have the right to use.
- YouTube ToS prohibits downloading without explicit permission from the rights holder.
- "CC-licensed" on a channel is not a blanket clearance — check the specific track.
- For sample use in releases: contact the rights holder or use a proper sample clearance service.
- Public domain audio (NASA, pre-1928 recordings, government works): generally safe, but verify jurisdiction.
