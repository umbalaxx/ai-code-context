# Code Context
Generated: 2026-06-02 08:52

## Project Structure
```
    .gitignore
    .python-version
    README.md
    code_context.md
    pyproject.toml
    uv.lock
    src/
        ai_code_context/
            __init__.py
            cx_script.py [M]
```

## Symbol Index

**src/ai_code_context/cx_script.py** ⚡
  def load_config() [line 58] — Returns (include_only, output_file).
  def is_binary() [line 104]
  def get_git_status() [line 113] — Returns dict of {filepath: status} for changed files.
  def get_git_changed_files() [line 129] — Returns list of files changed since last commit.
  def match_include() [line 140] — Returns the opts dict for the first include entry that matches rel_path,
  def extract_python_symbols() [line 164] — Extract top-level classes, functions, and their docstrings.
  def extract_imports() [line 194] — Extract what this file imports.
  def strip_python_comments() [line 214] — Remove # comments from Python source.
  def collect_files() [line 254] — Collect all files that should be included in the code context.
  def init() [line 286]
  def bundle() [line 302]
  def main() [line 400]

## Import Map

**src/ai_code_context/cx_script.py**
  ast
  os
  subprocess
  sys
  datetime → datetime
  pathlib → Path

## Source Files

### `README.md`
```md
# AI Code Context

This is a tool that generates a markdown file with the current state of the project. It is used to provide context to AI models when they are working on a project.

## Installation

Clone the repository and install the tool:

```bash
uv tool install .
```

## Usage

Go into the project directory and run:

```bash
code-context
```

## Configuration

The script is configured in `src/ai_code_context/cx_script.py`.

Your project level configuration lives in `.code-context/config.toml`.

You can modify the following settings:

- `OUTPUT_FILE`: The name of the output markdown file
- `IGNORED_DIRS`: Directories to ignore
- `IGNORED_FILES`: Files to ignore
- `IGNORED_SUFFIXES`: File extensions to ignore
- `INCLUDE_ONLY`: Specific files or directories to include (if non-empty, only these paths are bundled)
- `EXTRA_EXCLUDE`: Additional paths to exclude

```

### `pyproject.toml`
```toml
[project]
name = "ai-code-context"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
code-context = "ai_code_context.cx_script:main"

[build-system]
requires = ["uv_build>=0.8.9,<0.9.0"]
build-backend = "uv_build"

```

### `src/ai_code_context/__init__.py`
```py

```

### `src/ai_code_context/cx_script.py` ⚡ (modified)
```py
import ast
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli
    except ImportError:
        tomllib = None

# ── Configuration ────────────────────────────────────────────────────────────

OUTPUT_FILE = "code_context.md"

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "env",
    "dist",
    "build",
    ".code-context",
}


# Edit these directly when you want to be selective
# e.g. [("src/auth", {}), ("src/models/user.py", {"strip_comments": True})]
INCLUDE_ONLY = []

INCLUDE_README = True


DEFAULT_CONFIG = """\
# code-context configuration
output = "code_context.md"
include_readme = true

# Add files/dirs to include. Use strip_comments = true to strip Python comments.
# [[include]] # Include the scripts in the whole `src` directory
path = "src"
strip_comments = false

# [[include]] # You can include specific files
# path = "utils/util.py"
# strip_comments = false
"""


# ── Config loader ─────────────────────────────────────────────────────────────


def load_config() -> tuple[list, str]:
    """
    Returns (include_only, output_file).
    include_only is a list of (path_str, opts_dict) tuples.
    Falls back to module-level defaults if no config found.
    """
    config_path = Path(".code-context/config.toml")

    if not config_path.exists():
        # Prompt user to run code-context init first
        print(
            "⚠ No .code-context/config.toml found. Run 'code-context init' first to use custom config."
        )
        return INCLUDE_ONLY, OUTPUT_FILE

    if tomllib is None:
        print("⚠ Found .code-context/config.toml but no TOML parser available.")
        print("  Install one: pip install tomli  (or use Python 3.11+)")
        return INCLUDE_ONLY, OUTPUT_FILE

    print(f"✓ Using config: {config_path}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    output_file = raw.get("output", OUTPUT_FILE)
    include_readme = raw.get("include_readme", INCLUDE_README)

    # Parse [[include]] array of tables
    # Each entry: { path = "...", strip_comments = false }
    include_only = []
    if include_readme:
        include_only.append(("README.md", {}))
    for entry in raw.get("include", []):
        path = entry.get("path")
        if not path:
            continue
        opts = {k: v for k, v in entry.items() if k != "path"}
        include_only.append((path, opts))

    return include_only, output_file


# ── Helpers ───────────────────────────────────────────────────────────────────


def is_binary(path):
    try:
        with open(path, "tr", encoding="utf-8") as f:
            f.read(1024)
        return False
    except UnicodeDecodeError:
        return True


def get_git_status():
    """Returns dict of {filepath: status} for changed files."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        status = {}
        for line in result.stdout.strip().splitlines():
            if line.strip():
                code, path = line[:2].strip(), line[3:].strip()
                status[path] = code
        return status
    except Exception:
        return {}


def get_git_changed_files():
    """Returns list of files changed since last commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True
        )
        return set(result.stdout.strip().splitlines())
    except Exception:
        return set()


def match_include(rel_path: str, include_only: list) -> dict | None:
    """
    Returns the opts dict for the first include entry that matches rel_path,
    or None if no match.

    Matching rules:
      - Exact file match:   "src/foo/bar.py" matches only that file
      - Directory prefix:   "src/foo"        matches src/foo/bar.py, src/foo/baz/qux.py
      - Trailing slash:     "src/foo/"       same as directory prefix
    """
    for inc_path, opts in include_only:
        # Normalise: strip trailing slash
        inc = inc_path.rstrip("/")

        if rel_path == inc:
            return opts  # exact file match

        # Directory match: rel_path must start with inc + separator
        if rel_path.startswith(inc + "/") or rel_path.startswith(inc + os.sep):
            return opts

    return None


def extract_python_symbols(path):
    """Extract top-level classes, functions, and their docstrings."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        symbols = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.col_offset == 0:  # top-level only
                    doc = ast.get_docstring(node) or ""
                    symbols.append(
                        f"  def {node.name}() [line {node.lineno}]"
                        + (f" — {doc.splitlines()[0]}" if doc else "")
                    )
            elif isinstance(node, ast.ClassDef):
                if node.col_offset == 0:
                    doc = ast.get_docstring(node) or ""
                    symbols.append(
                        f"  class {node.name} [line {node.lineno}]"
                        + (f" — {doc.splitlines()[0]}" if doc else "")
                    )
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append(f"    .{item.name}() [line {item.lineno}]")
        return symbols
    except SyntaxError:
        return ["  (could not parse)"]


def extract_imports(path):
    """Extract what this file imports."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in node.names]
                imports.append(f"{module} → {', '.join(names)}")
        return imports
    except Exception:
        return []


def strip_python_comments(source: str) -> str:
    """Remove # comments from Python source."""

    lines = source.splitlines()

    # Remove inline and full-line # comments
    cleaned = []
    for line in lines:
        stripped = line.rstrip()
        # Remove inline comment, preserving indentation
        if "#" in stripped:
            # crude but effective: find first # not inside a string
            in_str = False
            quote_char = None
            for i, ch in enumerate(stripped):
                if ch in ('"', "'") and not in_str:
                    in_str = True
                    quote_char = ch
                elif ch == quote_char and in_str:
                    in_str = False
                elif ch == "#" and not in_str:
                    stripped = stripped[:i].rstrip()
                    break
        cleaned.append(stripped)

    # Collapse 3+ consecutive blank lines to 2
    result = []
    blank_count = 0
    for line in cleaned:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)

    return "\n".join(result)


def collect_files(include_only):
    """
    Collect all files that should be included in the code context.

    Args:
        include_only: List of (path_str, opts_dict) tuples from config

    Returns:
        List of relative file paths to include
    """

    if len(include_only) == 0:
        return []

    collected = []
    for root, dirs, files in os.walk("."):

        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, ".")

            if match_include(rel_path, include_only) is None:
                continue
            if is_binary(abs_path):
                continue

            collected.append(rel_path)
    return sorted(collected)


def init():
    config_dir = Path(".code-context")
    config_path = config_dir / "config.toml"

    if config_path.exists():
        print("⚠ .code-context/config.toml already exists. Aborting.")
        return

    config_dir.mkdir(exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    print(f"✓ Created {config_path}")


# ── Main ──────────────────────────────────────────────────────────────────────


def bundle():
    include_only, output_file = load_config()
    files = collect_files(include_only)
    git_status = get_git_status()
    git_changed = get_git_changed_files()

    with open(output_file, "w", encoding="utf-8") as out:

        # Header
        out.write("# Code Context\n")
        out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        # Directory tree
        out.write("## Project Structure\n```\n")
        for root, dirs, fs in os.walk("."):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            level = root.replace(".", "").count(os.sep)
            indent = "    " * level
            if root != ".":
                out.write(f"{indent}{os.path.basename(root)}/\n")

            for f in sorted(fs):
                rel = os.path.relpath(os.path.join(root, f), ".")
                marker = f" [{git_status[rel]}]" if rel in git_status else ""
                out.write(f"{indent}    {f}{marker}\n")
        out.write("```\n\n")

        # Symbol index — only for included files
        py_files = [f for f in files if f.endswith(".py")]
        if py_files:
            out.write("## Symbol Index\n")
            for path in py_files:
                symbols = extract_python_symbols(path)
                if symbols:
                    marker = " ⚡" if path in git_changed else ""
                    out.write(f"\n**{path}**{marker}\n")
                    out.write("\n".join(symbols) + "\n")
            out.write("\n")

        # Dependency map
        if py_files:
            out.write("## Import Map\n")
            for path in py_files:
                imports = extract_imports(path)
                if imports:
                    out.write(f"\n**{path}**\n")
                    for imp in imports:
                        out.write(f"  {imp}\n")
            out.write("\n")

        # Source files
        if include_only:
            out.write("## Source Files\n\n")
            for rel_path in files:
                opts = match_include(rel_path, include_only)
                if opts is None:
                    continue

                changed = " ⚡ (modified)" if rel_path in git_changed else ""
                ext = rel_path.rsplit(".", 1)[-1] if "." in rel_path else ""
                out.write(f"### `{rel_path}`{changed}\n```{ext}\n")
                try:
                    with open(rel_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    if opts.get("strip_comments") and ext == "py":
                        source = strip_python_comments(source)
                    out.write(source)
                except Exception as e:
                    out.write(f"// Error reading: {e}\n")
                out.write("\n```\n\n")

        # Footer / symtem prompt
        out.write("# System Prompt\n")
        out.write(
            "You are a code writer/analyst/review assistant who is proficient in Python and front-end development stack, e.g., HTML, Javascript, React. Your task is to analyze the provided code and respond to the user's instructions/questions/goals.\n\n"
        )

        out.write("# Rules:\n")
        out.write("- Be precise and concise, hit to the point.\n")
        out.write(
            "- If no instructions/goals are provided, do not over-analyze, make assumptions or suggest anything\n"
        )
        out.write(
            "- For Python, assume `uv` is the package manager and interpreter if not specified otherwise. Do not use `pip` with requirements.txt\n"
        )
        out.write(
            "- You can briefly (very concise) explain the code and point out some fixes (if any)\n\n"
        )

        out.write("# Intructions/questions/goals:\n")

    print(f"✓ {output_file} — {len(files)} files bundled")
    if include_only:
        print(f"  Selective: {[p for p, _ in include_only]}")
    if git_changed:
        print(f"  ⚡ {len(git_changed)} files changed since last commit")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init()
    else:
        bundle()


if __name__ == "__main__":
    main()

```

# System Prompt
You are a code writer/analyst/review assistant who is proficient in Python and front-end development stack, e.g., HTML, Javascript, React. Your task is to analyze the provided code and respond to the user's instructions/questions/goals.

# Rules:
- Be precise and concise, hit to the point.
- If no instructions/goals are provided, do not over-analyze, make assumptions or suggest anything
- For Python, assume `uv` is the package manager and interpreter if not specified otherwise. Do not use `pip` with requirements.txt
- You can briefly (very concise) explain the code and point out some fixes (if any)

# Intructions/questions/goals:
