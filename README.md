# 🔄 Shell Command Converter

A powerful Tkinter-based GUI tool that converts shell commands across multiple platforms.

## Features

✅ **Multi-platform Support**
- PowerShell, Bash, CMD, Python Script, Bat Script

✅ **Instant Conversion** (Tab 1)
- Paste in any format → others auto-fill
- No API required

✅ **AI-Powered Mode** (Tab 2, optional)
- OpenAI integration for complex cases
- Multi-select output formats
- Async processing

---

## Installation

```bash
pip install -r requirements.txt
python shell_converter.py
```

## Usage

### Tab 1: Programmatic (Instant)
- Paste any shell command
- Auto-converts to other 4 formats
- Supports: heredoc, python -c, raw scripts

### Tab 2: AI-Powered (Smart)
- Setup: copy `.env.example` to `.env`
- Add `OPENAI_API_KEY=sk-...`
- Paste command → select formats → Convert

## Configuration

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
```

## Supported Conversions

- PowerShell ↔ Bash (heredoc)
- PowerShell ↔ CMD (python -c)
- Any → Python/Bat via format conversion

## Performance

- Programmatic: < 50ms
- AI mode: 0.5–2s (API latency)

## Troubleshooting

- "Cannot extract Python code" → Use AI mode or paste valid heredoc/python -c
- API not working → Check `.env` has `OPENAI_API_KEY`
- App slow → AI takes 0.5–2s (normal)

---

**Happy converting!** 🚀