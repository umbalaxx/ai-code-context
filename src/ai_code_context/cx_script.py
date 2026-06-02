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


INCLUDE_ONLY = []

INCLUDE_README = True

AI_INSTRUCTION_FILES = ["CLAUDE.md", "AGENTS.md"]

CONTEXT_SENTINEL = ".code-context/code_context.md"

CONTEXT_INSTRUCTION = (
    "\n## Project Context (ai-code-context)\n\n"
    "Before starting any task, read `.code-context/code_context.md` for the full project context.\n"
    "Do not crawl individual source files unless asked.\n\n"
    "If the context file is missing, run `code-context` to generate it.\n\n"
    "### Refresh Context\n"
    "If you've made changes and need updated context, run:\n"
    "```bash\n"
    "code-context\n"
    "```\n"
)


DEFAULT_CONFIG = """\
# code-context configuration
output = "code_context.md"
include_readme = false
# tree_depth = 3  # limit folder tree depth (comment out for unlimited)

# Add files/dirs to include.
# mode: "full" (default) | "symbols" (symbol index only, no source block)
# symbols: list of symbol names — show only those symbols' source
# line_numbers: [start, end] — show only that line range (1-indexed, inclusive)
# strip_comments: strip Python # comments from source

[[include]] # Show only symbol index for the whole src directory
path = "src"
mode = "symbols"

# [[include]] # Override: show specific symbols from one file
# path = "src/mymodule/util.py"
# symbols = ["MyClass", "parse_config"]

# [[include]] # Override: show a specific line range
# path = "src/mymodule/handler.py"
# line_numbers = [45, 120]
"""


# ── Config loader ─────────────────────────────────────────────────────────────


def load_config() -> tuple[list, str, int | None]:
    """Returns (include_only, output_file, tree_depth)."""
    config_path = Path(".code-context/config.toml")

    if not config_path.exists():
        print(
            "⚠ No .code-context/config.toml found. Run 'code-context init' first to use custom config."
        )
        return INCLUDE_ONLY, OUTPUT_FILE, None

    if tomllib is None:
        print("⚠ Found .code-context/config.toml but no TOML parser available.")
        print("  Install one: pip install tomli  (or use Python 3.11+)")
        return INCLUDE_ONLY, OUTPUT_FILE, None

    print(f"✓ Using config: {config_path}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    output_file = raw.get("output", OUTPUT_FILE)
    include_readme = raw.get("include_readme", INCLUDE_README)
    tree_depth = raw.get("tree_depth", None)

    include_only = []
    if include_readme:
        include_only.append(("README.md", {}))
    for entry in raw.get("include", []):
        path = entry.get("path")
        if not path:
            continue
        opts = {k: v for k, v in entry.items() if k != "path"}
        include_only.append((path, opts))

    return include_only, output_file, tree_depth


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
    Returns the opts dict for the most specific (longest prefix) include entry
    that matches rel_path, or None if no match.

    Matching rules:
      - Exact file match:   "src/foo/bar.py" matches only that file
      - Directory prefix:   "src/foo"        matches src/foo/bar.py, src/foo/baz/qux.py
      - Trailing slash:     "src/foo/"       same as directory prefix
    More specific (longer) paths take priority over shorter ones.
    """
    best_opts = None
    best_len = -1
    for inc_path, opts in include_only:
        inc = inc_path.rstrip("/")
        matched = (
            rel_path == inc
            or rel_path.startswith(inc + "/")
            or rel_path.startswith(inc + os.sep)
        )
        if matched and len(inc) > best_len:
            best_len = len(inc)
            best_opts = opts
    return best_opts


def extract_python_symbols(path, filter_names=None):
    """Extract top-level classes, functions, and their docstrings."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        name_set = set(filter_names) if filter_names else None
        symbols = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.col_offset == 0:
                    if name_set is None or node.name in name_set:
                        doc = ast.get_docstring(node) or ""
                        symbols.append(
                            f"  def {node.name}() [line {node.lineno}]"
                            + (f" — {doc.splitlines()[0]}" if doc else "")
                        )
            elif isinstance(node, ast.ClassDef):
                if node.col_offset == 0:
                    if name_set is None or node.name in name_set:
                        doc = ast.get_docstring(node) or ""
                        symbols.append(
                            f"  class {node.name} [line {node.lineno}]"
                            + (f" — {doc.splitlines()[0]}" if doc else "")
                        )
                        for item in node.body:
                            if isinstance(
                                item, (ast.FunctionDef, ast.AsyncFunctionDef)
                            ):
                                symbols.append(
                                    f"    .{item.name}() [line {item.lineno}]"
                                )
        return symbols
    except SyntaxError:
        return ["  (could not parse)"]


def extract_symbol_source(path: str, names: list) -> str:
    """Extract source of named top-level symbols from a Python file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        source = "".join(lines)
        tree = ast.parse(source)
        name_set = set(names)
        chunks = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in name_set:
                    chunk = "".join(lines[node.lineno - 1 : node.end_lineno])
                    chunks.append(chunk.rstrip())
        return "\n\n".join(chunks)
    except Exception as e:
        return f"# Error extracting symbols: {e}"


def extract_line_range(path: str, start: int, end: int) -> str:
    """Extract lines start..end (1-indexed, inclusive) from a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[start - 1 : end]).rstrip()
    except Exception as e:
        return f"# Error reading lines: {e}"


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

    cleaned = []
    for line in lines:
        stripped = line.rstrip()
        if "#" in stripped:
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
    """Collect all files that should be included in the code context."""

    if len(include_only) == 0:
        return []

    collected = []
    for root, _, files in os.walk("."):

        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, ".")

            if match_include(rel_path, include_only) is None:
                continue
            if is_binary(abs_path):
                continue

            collected.append(rel_path)
    return sorted(collected)


def code_fence(source: str) -> str:
    """Return the shortest backtick fence that won't collide with content."""
    max_run = 0
    run = 0
    for ch in source:
        if ch == "`":
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return "`" * max(3, max_run + 1)


def add_to_gitignore():
    """Add code-context to gitignore"""

    gitignore_path = Path(".gitignore")
    entry = "\n# code-context\n.code-context/\n"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if ".code-context" not in content:
            gitignore_path.write_text(content + entry, encoding="utf-8")
            print("✓ Added .code-context/ to .gitignore")
        else:
            print("✓ .code-context/ already in .gitignore")
    else:
        gitignore_path.write_text(entry.lstrip(), encoding="utf-8")
        print("✓ Created .gitignore with .code-context/")


def add_ai_instructions():
    """Inject code-context instructions into AI context files (CLAUDE.md, AGENTS.md, etc.)"""
    for filename in AI_INSTRUCTION_FILES:
        path = Path(filename)
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if CONTEXT_SENTINEL in content:
                print(f"✓ {filename} already has code-context instructions")
            else:
                path.write_text(content + CONTEXT_INSTRUCTION, encoding="utf-8")
                print(f"✓ Added code-context instructions to {filename}")
        else:
            path.write_text(CONTEXT_INSTRUCTION.lstrip(), encoding="utf-8")
            print(f"✓ Created {filename}")


def init():
    config_dir = Path(".code-context")
    config_path = config_dir / "config.toml"

    if config_path.exists():
        print("⚠ .code-context/config.toml already exists. Aborting.")
        return

    config_dir.mkdir(exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")

    add_to_gitignore()
    add_ai_instructions()
    print(f"✓ Created {config_path}")


# ── Main ──────────────────────────────────────────────────────────────────────


def bundle():
    include_only, output_file, tree_depth = load_config()
    files = collect_files(include_only)
    git_status = get_git_status()
    git_changed = get_git_changed_files()

    config_dir = Path(".code-context")
    output_path = config_dir / output_file

    config_dir.mkdir(exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out:

        # Header
        out.write("# Code Context\n")
        out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        # Directory tree
        out.write("## Project Structure\n```\n")
        for root, dirs, fs in os.walk("."):
            dirs[:] = sorted([d for d in dirs if d not in IGNORED_DIRS])
            level = root.replace(".", "").count(os.sep)
            if tree_depth is not None and level >= tree_depth:
                dirs[:] = []  # stop recursing past max depth
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
                opts = match_include(path, include_only) or {}
                filter_names = opts.get("symbols")
                symbols = extract_python_symbols(path, filter_names)
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

                mode = opts.get("mode", "full")
                symbols_filter = opts.get("symbols")
                line_numbers = opts.get("line_numbers")

                # mode="symbols" with no further override: skip source block entirely
                if (
                    mode == "symbols"
                    and symbols_filter is None
                    and line_numbers is None
                ):
                    continue

                changed = " ⚡ (modified)" if rel_path in git_changed else ""
                ext = rel_path.rsplit(".", 1)[-1] if "." in rel_path else ""

                annotation = ""
                if symbols_filter is not None:
                    annotation = f" (symbols: {', '.join(symbols_filter)})"
                elif line_numbers is not None:
                    annotation = f" (lines {line_numbers[0]}–{line_numbers[1]})"

                try:
                    if symbols_filter is not None and ext == "py":
                        source = extract_symbol_source(rel_path, symbols_filter)
                    elif line_numbers is not None:
                        source = extract_line_range(
                            rel_path, line_numbers[0], line_numbers[1]
                        )
                    else:
                        with open(rel_path, "r", encoding="utf-8") as f:
                            source = f.read()
                    if opts.get("strip_comments") and ext == "py":
                        source = strip_python_comments(source)
                except Exception as e:
                    source = f"// Error reading: {e}"

                fence = code_fence(source)
                out.write(f"### `{rel_path}`{changed}{annotation}\n{fence}{ext}\n")
                out.write(source)
                out.write(f"\n{fence}\n\n")

        # Footer / system prompt
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

    add_to_gitignore()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init()
    else:
        config_path = Path(".code-context/config.toml")

        if not config_path.exists():
            print("⚠ No .code-context/config.toml found. Automatically initializing...")
            init()
        bundle()


if __name__ == "__main__":
    main()
