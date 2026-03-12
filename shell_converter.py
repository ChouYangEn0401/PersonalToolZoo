"""
Shell Command Converter — Tkinter GUI
======================================
Multi-platform shell command converter supporting:
  • PowerShell, Bash, CMD, Python Script, Bat Script
  
Two conversion modes:
  1. Programmatic: Instant conversion (no API)
  2. AI-Powered:   Smart parsing via OpenAI (requires API key in .env)
"""

from __future__ import annotations
import os
import re
import threading
import textwrap
import tkinter as tk
from tkinter import ttk

# ── Optional dependencies ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI as _OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ═════════════════════════════════════════════════════════════════════════════════
#  UI Theme Configuration
# ═════════════════════════════════════════════════════════════════════════════════

class Theme:
    """Dark theme colors and fonts."""
    BG = "#1e1f22"
    BG_PANEL = "#2b2d30"
    BG_TEXT = "#1e1f22"
    FG = "#bcbec4"
    FG_LABEL = "#ffffff"
    FG_MUTED = "#888888"
    FG_ERROR = "#d04040"
    ACCENT_SOURCE = "#f0a500"  # Orange – source input
    ACCENT_OUTPUT = "#2a9d5c"  # Green  – converted output
    ACCENT_IDLE = "#3c3f41"    # Grey   – idle state
    MONO = ("JetBrains Mono", 10) if os.name == "nt" else ("Menlo", 10)


# Format identifiers
FORMATS = ["PowerShell", "Bash", "CMD", "Python Script", "Bat Script"]

# ═════════════════════════════════════════════════════════════════════════════════
#  Shell Command Extraction & Conversion Logic
# ═════════════════════════════════════════════════════════════════════════════════

class HereditocExtractor:
    """Extract Python code from heredoc syntax (<<'PY' ... PY)."""
    PATTERN = re.compile(
        r"<<['\"]?(?:PY|PYTHON|EOF|END)['\"]?\s*\n(.*?)\n[ \t]*(?:PY|PYTHON|EOF|END)[ \t]*$",
        re.DOTALL | re.MULTILINE,
    )

    @classmethod
    def extract(cls, text: str) -> str | None:
        """Extract heredoc body; return None if not found."""
        match = cls.PATTERN.search(text)
        return match.group(1).strip() if match else None


class CPythonFlagExtractor:
    """Extract Python code from `python -c "..."` syntax."""
    PATTERN = re.compile(
        r'python(?:\S*\s+)?-c\s+(?P<q>["\'])(?P<code>.+?)(?P=q)', re.DOTALL
    )

    @classmethod
    def extract(cls, text: str) -> str | None:
        """Extract code from -c flag; return None if not found."""
        match = cls.PATTERN.search(text)
        if not match:
            return None
        code = match.group("code")
        # Unescape embedded newlines and quotes
        code = code.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
        return code.strip()


def get_python_code(source_format: str, text: str) -> str | None:
    """
    Extract embedded Python code from any shell format.
    
    Args:
        source_format: One of FORMATS (e.g., 'PowerShell', 'CMD')
        text: Raw input text
    
    Returns:
        Extracted Python code, or None if not recognized
    """
    text = text.strip()
    if not text:
        return None

    # Already raw Python
    if source_format == "Python Script":
        return text

    # Try heredoc and -c flag extraction
    code = HereditocExtractor.extract(text) or CPythonFlagExtractor.extract(text)
    if code:
        return code

    # For Bat/CMD, try parsing echoed lines
    if source_format == "Bat Script":
        return _extract_from_bat_echo_lines(text)

    return None


def _extract_from_bat_echo_lines(text: str) -> str | None:
    """Extract Python from BAT echo statements."""
    # Collapse ^ continuations
    flat = re.sub(r"\s*\^\s*\r?\n\s*", " ", text)
    code = CPythonFlagExtractor.extract(flat)
    if code:
        return code
    
    # Parse echo statements
    lines = []
    for raw in text.splitlines():
        match = re.match(r"^echo\s+(.+)$", raw.strip(), re.IGNORECASE)
        if match:
            lines.append(match.group(1).replace("%%", "%"))
    return "\n".join(lines) if lines else None


# ───────────────────────────────────────────────────────────────────────────────
#  Output Emitters (convert Python to target format)
# ───────────────────────────────────────────────────────────────────────────────

class ShellEmitter:
    """Base class for shell code generators."""

    @staticmethod
    def to_powershell(code: str) -> str:
        """Emit PowerShell heredoc wrapper."""
        return f"& .\\.venv\\Scripts\\python.exe - <<'PY'\n{code}\nPY"

    @staticmethod
    def to_bash(code: str) -> str:
        """Emit Bash heredoc wrapper."""
        return f"./.venv/bin/python3 - <<'PY'\n{code}\nPY"

    @staticmethod
    def to_cmd(code: str) -> str:
        """Emit CMD one-liner using -c flag."""
        lines = [l.rstrip() for l in code.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        one_liner = "; ".join(lines).replace('"', '\\"')
        return f'python -c "{one_liner}"'

    @staticmethod
    def to_python_script(code: str) -> str:
        """Return code as-is (already Python)."""
        return code

    @staticmethod
    def to_bat_script(code: str) -> str:
        """Emit BAT script using temp file approach."""
        bat_lines = [
            "@echo off",
            "set _TMP=%TEMP%\\__conv_script.py",
            "(",
        ]
        for line in code.splitlines():
            bat_lines.append(f"    echo {line.replace('%', '%%')}")
        bat_lines.extend([
            ") > %_TMP%",
            ".venv\\Scripts\\python.exe %_TMP%",
            "del %_TMP%",
        ])
        return "\n".join(bat_lines)


# Format → emitter mapping
EMITTERS = {
    "PowerShell":    ShellEmitter.to_powershell,
    "Bash":          ShellEmitter.to_bash,
    "CMD":           ShellEmitter.to_cmd,
    "Python Script": ShellEmitter.to_python_script,
    "Bat Script":    ShellEmitter.to_bat_script,
}


def convert_all(source_format: str, text: str) -> dict[str, str]:
    """
    Convert Python code to all target formats.
    
    Args:
        source_format: Source format name
        text: Raw input from source
    
    Returns:
        Dict mapping format names → converted code
    """
    code = get_python_code(source_format, text)
    if not code:
        return {}
    return {
        name: fn(code)
        for name, fn in EMITTERS.items()
        if name != source_format
    }


# ═════════════════════════════════════════════════════════════════════════════════
#  AI-Powered Conversion (OpenAI)
# ═════════════════════════════════════════════════════════════════════════════════

class AIConverter:
    """AI-powered shell command converter using OpenAI."""

    SYSTEM_PROMPT = textwrap.dedent("""\
        You are a shell-command converter expert.
        The user provides a command snippet and target shell formats.
        Convert it accurately for each requested format.

        Rules:
        - Preserve exact logic and script content.
        - Use .venv paths:
          * Windows: .venv\\Scripts\\python.exe
          * Unix: .venv/bin/python3
        - For CMD/Bat use temp-file approach for multi-line scripts.
        - Return ONLY the conversions using exact section markers below.

        Response format (omit unrequested sections):
        ===PowerShell===
        <code>
        ===Bash===
        <code>
        ===CMD===
        <code>
        ===Python Script===
        <code>
        ===Bat Script===
        <code>
    """)

    # ### REFACTOR: may be use `ntu_easy_llm` will be a better practice ?? ###
    @classmethod
    def convert(cls, source_text: str, target_formats: list[str]) -> dict[str, str]:
        """
        Convert shell command to multiple target formats using OpenAI.
        
        Args:
            source_text: Raw shell command input
            target_formats: List of target formats (e.g., ['Bash', 'CMD'])
        
        Returns:
            Dict mapping format names → converted code
        
        Raises:
            ValueError: If API key not configured
            Exception: On API errors
        """
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not api_key or api_key.startswith("sk-..."):
            raise ValueError(
                "OPENAI_API_KEY not set in .env\n"
                "Copy .env.example to .env and fill in your key."
            )

        client = _OpenAI(api_key=api_key)
        user_msg = (
            f"Convert to: {', '.join(target_formats)}\n\n"
            f"```\n{source_text.strip()}\n```"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": cls.SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.05,
        )

        raw_response = response.choices[0].message.content
        return cls._parse_response(raw_response)
    # ### REFACTOR: may be use `ntu_easy_llm` will be a better practice ?? ###

    @staticmethod
    def _parse_response(raw: str) -> dict[str, str]:
        """Parse AI response into format → code mapping."""
        results: dict[str, str] = {}
        parts = re.split(r"===(.+?)===", raw)

        for i in range(1, len(parts), 2):
            format_name = parts[i].strip()
            body = parts[i + 1].strip() if (i + 1) < len(parts) else ""

            # Remove markdown code fences
            body = re.sub(r"^```[\w-]*\n", "", body)
            body = re.sub(r"\n```$", "", body)
            results[format_name] = body.strip()

        return results


# ═════════════════════════════════════════════════════════════════════════════════
#  UI Components
# ═════════════════════════════════════════════════════════════════════════════════

class BorderedText(tk.Frame):
    """Text widget wrapped in a colored Frame acting as a border."""

    def __init__(self, master, border_color=Theme.ACCENT_IDLE, height=8, **kw):
        super().__init__(master, background=border_color, padx=2, pady=2)
        self.text = tk.Text(
            self,
            height=height,
            bg=Theme.BG_TEXT,
            fg=Theme.FG,
            insertbackground=Theme.FG,
            font=Theme.MONO,
            relief="flat",
            wrap="none",
            undo=True,
            **kw,
        )
        # Scrollbars
        hbar = tk.Scrollbar(
            self, orient="horizontal", command=self.text.xview,
            bg=Theme.BG_PANEL, troughcolor=Theme.BG
        )
        vbar = tk.Scrollbar(
            self, orient="vertical", command=self.text.yview,
            bg=Theme.BG_PANEL, troughcolor=Theme.BG
        )
        self.text.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def set_border_color(self, color: str):
        """Change border color."""
        self.configure(background=color)

    def get_text(self) -> str:
        """Get all text content."""
        return self.text.get("1.0", "end-1c")

    def set_text(self, value: str):
        """Replace all text content."""
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)

    def bind_event(self, event: str, callback):
        """Bind event to text widget."""
        self.text.bind(event, callback)


def create_label(parent, text: str, **kw) -> tk.Label:
    """Create a styled label."""
    return tk.Label(
        parent, text=text,
        bg=Theme.BG_PANEL, fg=Theme.FG_LABEL,
        font=("Segoe UI", 9, "bold"),
        anchor="w",
        **kw,
    )


# ═════════════════════════════════════════════════════════════════════════════════
#  Tab 1: Programmatic Converter
# ═════════════════════════════════════════════════════════════════════════════════

class ProgrammaticTab(tk.Frame):
    """Tab for instant format conversion (no API needed)."""

    def __init__(self, master):
        super().__init__(master, bg=Theme.BG_PANEL)
        self._busy = False  # Re-entrancy guard
        self._areas: dict[str, BorderedText] = {}
        self._build()

    def _build(self):
        """Construct UI components."""
        self._build_header()
        self._build_legend()
        self._build_status_bar()
        self._build_text_areas()

    def _build_header(self):
        """Build header label."""
        tk.Label(
            self,
            text="Paste any format → others auto-fill instantly",
            bg=Theme.BG_PANEL, fg=Theme.FG_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="top", anchor="w", padx=12, pady=(8, 4))

    def _build_legend(self):
        """Build color legend."""
        legend_frame = tk.Frame(self, bg=Theme.BG_PANEL)
        legend_frame.pack(side="top", anchor="w", padx=12, pady=(0, 6))

        legend_items = [
            (Theme.ACCENT_SOURCE, "source"),
            (Theme.ACCENT_OUTPUT, "converted"),
            (Theme.ACCENT_IDLE, "idle"),
        ]
        for color, label in legend_items:
            canvas = tk.Canvas(
                legend_frame, width=12, height=12, bg=Theme.BG_PANEL,
                highlightthickness=0
            )
            canvas.create_rectangle(0, 0, 12, 12, fill=color, outline="")
            canvas.pack(side="left", padx=(0, 3))
            tk.Label(
                legend_frame, text=label,
                bg=Theme.BG_PANEL, fg=Theme.FG_MUTED,
                font=("Segoe UI", 8)
            ).pack(side="left", padx=(0, 12))

    def _build_status_bar(self):
        """Build status message display."""
        self._status_var = tk.StringVar(value="")
        tk.Label(
            self, textvariable=self._status_var,
            bg=Theme.BG_PANEL, fg=Theme.ACCENT_OUTPUT,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="bottom", fill="x", padx=12, pady=(0, 6))

    def _build_text_areas(self):
        """Build scrollable text area container."""
        canvas = tk.Canvas(
            self, bg=Theme.BG_PANEL, highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=4)

        container = tk.Frame(canvas, bg=Theme.BG_PANEL)
        canvas.create_window((0, 0), window=container, anchor="nw", tags="frame")

        def _on_canvas_resize(e):
            canvas.itemconfig("frame", width=e.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # Mouse wheel scrolling
        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_wheel)

        # Create text area for each format
        for fmt in FORMATS:
            self._create_format_area(container, fmt)

    def _create_format_area(self, parent, fmt: str):
        """Create a labeled text area for given format."""
        row = tk.Frame(parent, bg=Theme.BG_PANEL)
        row.pack(fill="x", pady=6)

        create_label(row, fmt).pack(side="top", anchor="w")
        text_area = BorderedText(row, border_color=Theme.ACCENT_IDLE, height=6)
        text_area.pack(fill="x", expand=True)
        self._areas[fmt] = text_area

        # Bind change events
        def _on_change(event, name=fmt):
            self.after(1, lambda n=name: self._on_text_changed(n))

        text_area.bind_event("<<Paste>>", _on_change)
        text_area.bind_event("<KeyRelease>", _on_change)

    def _on_text_changed(self, src_format: str):
        """Handle text change in any format area."""
        if self._busy:
            return
        self._busy = True
        try:
            text = self._areas[src_format].get_text()

            # Update border colors
            for name, area in self._areas.items():
                color = Theme.ACCENT_SOURCE if name == src_format else Theme.ACCENT_IDLE
                area.set_border_color(color)

            # Convert to other formats
            results = convert_all(src_format, text)
            if results:
                for name, converted_code in results.items():
                    self._areas[name].set_text(converted_code)
                    self._areas[name].set_border_color(Theme.ACCENT_OUTPUT)
                self._status_var.set(f"✓  Converted from {src_format}")
            elif text.strip():
                self._status_var.set(
                    "⚠  Cannot extract Python code — "
                    "paste a heredoc or python -c command"
                )
            else:
                self._status_var.set("")
        finally:
            self._busy = False


# ═════════════════════════════════════════════════════════════════════════════════
#  Tab 2: AI-Powered Converter
# ═════════════════════════════════════════════════════════════════════════════════

class AITab(tk.Frame):
    """Tab for AI-powered conversion (requires OpenAI API)."""

    def __init__(self, master):
        super().__init__(master, bg=Theme.BG_PANEL)
        self._output_widgets: list[tuple[tk.Label, BorderedText]] = []
        self._build()

    def _build(self):
        """Construct UI components."""
        self._build_header()
        self._build_input_area()
        self._build_controls()
        self._build_output_area()

    def _build_header(self):
        """Build header label."""
        tk.Label(
            self,
            text="AI converts any format — paste anything, select outputs, click Convert",
            bg=Theme.BG_PANEL, fg=Theme.FG_MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="top", anchor="w", padx=12, pady=(8, 4))

    def _build_input_area(self):
        """Build input text area."""
        input_frame = tk.Frame(self, bg=Theme.BG_PANEL)
        input_frame.pack(fill="x", padx=12, pady=(0, 6))
        create_label(input_frame, "Input (any format)").pack(anchor="w")
        self._input = BorderedText(
            input_frame, border_color=Theme.ACCENT_SOURCE, height=8
        )
        self._input.pack(fill="x")

    def _build_controls(self):
        """Build format selection and convert button."""
        ctrl_frame = tk.Frame(self, bg=Theme.BG_PANEL)
        ctrl_frame.pack(fill="x", padx=12, pady=6)

        # Format selector
        list_frame = tk.Frame(ctrl_frame, bg=Theme.BG_PANEL)
        list_frame.pack(side="left")
        create_label(list_frame, "Target formats (Ctrl+click)").pack(anchor="w")
        
        self._listbox = tk.Listbox(
            list_frame,
            selectmode="multiple",
            bg=Theme.BG_TEXT, fg=Theme.FG,
            selectbackground=Theme.ACCENT_SOURCE,
            selectforeground="#000000",
            font=("Segoe UI", 9),
            height=5, width=20,
            relief="flat", bd=1,
            highlightthickness=1,
            highlightcolor=Theme.ACCENT_IDLE,
            highlightbackground=Theme.ACCENT_IDLE,
            exportselection=False,
        )
        for fmt in FORMATS:
            self._listbox.insert("end", fmt)
        self._listbox.selection_set(0, "end")  # Select all by default
        self._listbox.pack()
        self._listbox.bind("<<ListboxSelect>>", self._on_format_selected)

        # Button and status
        btn_frame = tk.Frame(ctrl_frame, bg=Theme.BG_PANEL)
        btn_frame.pack(side="left", padx=20, anchor="n")
        
        self._convert_btn = tk.Button(
            btn_frame,
            text="⚡  Convert with AI",
            bg=Theme.ACCENT_SOURCE, fg="#000000",
            activebackground="#c8880a",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=14, pady=8,
            cursor="hand2",
            command=self._on_convert_clicked,
        )
        self._convert_btn.pack(pady=(18, 6))

        self._status_var = tk.StringVar(value="")
        tk.Label(
            btn_frame,
            textvariable=self._status_var,
            bg=Theme.BG_PANEL, fg=Theme.ACCENT_OUTPUT,
            font=("Segoe UI", 9),
            wraplength=260,
            justify="left",
        ).pack(anchor="w")

    def _build_output_area(self):
        """Build scrollable output area."""
        out_label_frame = tk.Frame(self, bg=Theme.BG_PANEL)
        out_label_frame.pack(fill="x", padx=12)
        create_label(out_label_frame, "Output").pack(anchor="w")

        canvas_frame = tk.Frame(self, bg=Theme.BG_PANEL)
        canvas_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self._canvas = tk.Canvas(
            canvas_frame, bg=Theme.BG_PANEL, highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._out_container = tk.Frame(self._canvas, bg=Theme.BG_PANEL)
        self._canvas.create_window(
            (0, 0), window=self._out_container, anchor="nw", tags="frame"
        )

        def _on_canvas_resize(e):
            self._canvas.itemconfig("frame", width=e.width)

        self._canvas.bind("<Configure>", _on_canvas_resize)
        self._out_container.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )

        # Mouse wheel scrolling
        def _on_wheel(e):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self._canvas.bind_all("<MouseWheel>", _on_wheel)

        # Create output boxes for default selection
        self._rebuild_output_areas(FORMATS)

    def _get_selected_formats(self) -> list[str]:
        """Get currently selected formats from listbox."""
        return [FORMATS[i] for i in self._listbox.curselection()]

    def _on_format_selected(self, _event=None):
        """Handle format selection change."""
        selected = self._get_selected_formats()
        self._rebuild_output_areas(selected)

    def _rebuild_output_areas(self, formats: list[str]):
        """Rebuild output text areas for selected formats."""
        # Preserve existing text
        existing_text: dict[str, str] = {}
        for lbl, text_area in self._output_widgets:
            fmt_name = lbl.cget("text")
            existing_text[fmt_name] = text_area.get_text()

        # Clear old widgets
        for widget in self._out_container.winfo_children():
            widget.destroy()
        self._output_widgets.clear()

        if not formats:
            tk.Label(
                self._out_container,
                text="— select at least one format above —",
                bg=Theme.BG_PANEL, fg="#555555",
                font=("Segoe UI", 9),
            ).pack(pady=20)
            return

        for fmt in formats:
            row = tk.Frame(self._out_container, bg=Theme.BG_PANEL)
            row.pack(fill="x", pady=5)

            lbl = create_label(row, fmt)
            lbl.pack(anchor="w")

            text_area = BorderedText(
                row, border_color=Theme.ACCENT_IDLE, height=6
            )
            text_area.pack(fill="x")

            # Restore previous text if available
            if fmt in existing_text and existing_text[fmt]:
                text_area.set_text(existing_text[fmt])

            self._output_widgets.append((lbl, text_area))

    def _on_convert_clicked(self):
        """Handle Convert button click."""
        src = self._input.get_text().strip()
        targets = self._get_selected_formats()

        if not src:
            self._status_var.set("⚠  Paste a command in the Input box first")
            return
        if not targets:
            self._status_var.set("⚠  Select at least one target format")
            return
        if not OPENAI_AVAILABLE:
            self._status_var.set("✗  openai package not installed")
            return

        self._convert_btn.configure(state="disabled", text="⏳  Converting…")
        self._status_var.set("Calling OpenAI API…")

        def _worker():
            try:
                results = AIConverter.convert(src, targets)
                self.after(0, lambda r=results: self._apply_results(r, targets))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_results(self, results: dict[str, str], targets: list[str]):
        """Apply conversion results to output areas."""
        format_to_area = {
            lbl.cget("text"): text_area
            for lbl, text_area in self._output_widgets
        }
        for fmt in targets:
            if fmt in format_to_area:
                code = results.get(fmt, "(no result)")
                format_to_area[fmt].set_text(code)
                format_to_area[fmt].set_border_color(Theme.ACCENT_OUTPUT)

        success_count = sum(1 for f in targets if f in results)
        self._status_var.set(f"✓  Done ({success_count}/{len(targets)} formats)")
        self._convert_btn.configure(state="normal", text="⚡  Convert with AI")

    def _on_error(self, exc: Exception):
        """Handle conversion error."""
        self._status_var.set(f"✗  {exc}")
        self._convert_btn.configure(state="normal", text="⚡  Convert with AI")


# ═════════════════════════════════════════════════════════════════════════════════
#  Main Application
# ═════════════════════════════════════════════════════════════════════════════════

class ShellConverterApp:
    """Main application window."""

    def __init__(self):
        self.root = tk.Tk()
        self._configure_window()
        self._build_ui()

    def _configure_window(self):
        """Configure root window."""
        self.root.title("Shell Command Converter")
        self.root.geometry("860x700")
        self.root.minsize(640, 480)
        self.root.configure(bg=Theme.BG)

    def _build_ui(self):
        """Build main UI."""
        self._apply_theme()
        self._build_title_bar()
        self._build_notebook()

    def _apply_theme(self):
        """Apply dark theme to ttk widgets."""
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TNotebook",
            background=Theme.BG,
            borderwidth=0,
            tabmargins=[0, 0, 0, 0],
        )
        style.configure(
            "TNotebook.Tab",
            background=Theme.BG_PANEL,
            foreground=Theme.FG_MUTED,
            padding=[16, 6],
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", Theme.BG_PANEL)],
            foreground=[("selected", Theme.FG_LABEL)],
        )
        style.configure(
            "TScrollbar",
            background=Theme.BG_PANEL,
            troughcolor=Theme.BG,
            arrowcolor=Theme.FG,
            borderwidth=0,
        )

    def _build_title_bar(self):
        """Build title bar."""
        title_bar = tk.Frame(self.root, bg=Theme.BG, pady=10)
        title_bar.pack(side="top", fill="x", padx=16)

        tk.Label(
            title_bar,
            text="🔄  Shell Command Converter",
            bg=Theme.BG,
            fg=Theme.FG_LABEL,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        tk.Label(
            title_bar,
            text="PowerShell · Bash · CMD · Python Script · Bat Script",
            bg=Theme.BG,
            fg="#555555",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12)

    def _build_notebook(self):
        """Build tabbed interface."""
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tab_programmatic = ProgrammaticTab(notebook)
        tab_ai = AITab(notebook)

        notebook.add(tab_programmatic, text="  ⚙  Programmatic  ")
        notebook.add(tab_ai, text="  🤖  AI-Powered  ")

    def run(self):
        """Start the application."""
        self.root.mainloop()


def main():
    """Application entry point."""
    app = ShellConverterApp()
    app.run()


if __name__ == "__main__":
    main()
