## AIADR — AI-Assisted Data Review

[![CI](https://github.com/dvoulgaridis/AIADR/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/dvoulgaridis/AIADR/actions/workflows/ci.yml)

AIADR assists with reviewing and redacting images, documents and audio files. It creates editable redaction layers, renders deterministic redacted outputs and exports a lightweight audit bundle. Review behavior comes from portable instruction sets; GDPR and CCPA/CPRA sets are supplied. AIADR does not guarantee legal compliance.

> [!CAUTION]
> AIADR runs locally, but inference may not. Content submitted for analysis is sent to the model endpoint you configure. Use a local model endpoint if source material must not leave your machine.

### Requirements

- Python 3.11+
- uv
- Node.js 22.13+
- pnpm 11.9.0
- .NET SDK 10
- LibreOffice
- FFmpeg

### Quick Start

```sh
git clone https://github.com/dvoulgaridis/AIADR.git
cd AIADR
uv sync --all-packages
pnpm install
uv run python scripts/publish_docx_processor.py
pnpm --dir frontend run build
uv run python main.py
```

Open `http://127.0.0.1:7860`.

For development, build the Debug DOCX processor once:

```sh
dotnet restore docx-processor/Aiadr.Docx.csproj --locked-mode
dotnet build docx-processor/Aiadr.Docx.csproj --no-restore
```

Then run the backend and frontend in separate terminals.

Terminal 1:

```sh
uv run python main.py dev
```

Terminal 2:

```sh
pnpm --dir frontend run dev -- --port 5173
```

Open `http://localhost:5173/`.

### Supported Formats

| Source kind | File extensions |
| ----------- | ------------------- |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp` |
| Documents | `.csv`, `.docx`, `.pdf`, `.txt` |
| Audio | `.aac`, `.flac`, `.m4a`, `.mp3`, `.mp4`, `.ogg`, `.opus`, `.wav`, `.webm` |
