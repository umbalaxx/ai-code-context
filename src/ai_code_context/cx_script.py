import ast
import os
import subprocess
from datetime import datetime

import pathspec

# ── Configuration ────────────────────────────────────────────────────────────

OUTPUT_FILE = "code_context.md"
SCRIPT_NAME = os.path.basename(__file__)

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "env",
    "dist",
    "build",
    "secret",
    "secrets",
}
IGNORED_FILES = {
    OUTPUT_FILE,
    SCRIPT_NAME,
    ".env",
    "uv.lock",
    ".python-version",
    ".gitignore",
}
IGNORED_SUFFIXES = {
    ".txt",
    ".log",
    ".json",
    ".csv",
    ".ipynb",
    ".xml",
    ".yaml",
    ".yml",
    ".pdf",
    ".sh",
    ".toml",
    ".html",
    ".zip",
    ".archive",
    ".bib",
}

# Edit these directly when you want to be selective
INCLUDE_ONLY = [
    ("src/pdf_summarizer/data_types.py", {"strip_comments": True}),
    ("src/pdf_summarizer/main.py", {"strip_comments": False}),
]  # if non-empty, only bundle these paths e.g. ["src/auth", "src/models/user.py"]
EXTRA_EXCLUDE = [
    "mongodb-backups",
    "markdowns",
]  # additional paths to skip e.g. ["src/legacy", "tests"]

# ── Helpers ───────────────────────────────────────────────────────────────────


def load_gitignore():
    if os.path.exists(".gitignore"):
        with open(".gitignore", "r", encoding="utf-8") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f.readlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", [])


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
    """Remove # comments and docstrings from Python source."""

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


def collect_files(spec):
    collected = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [
            d
            for d in dirs
            if d not in IGNORED_DIRS and not spec.match_file(os.path.join(root, d))
        ]
        for file in files:
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, ".")

            if file in IGNORED_FILES:
                continue
            if any(file.endswith(suffix) for suffix in IGNORED_SUFFIXES):
                continue
            if spec.match_file(rel_path):
                continue
            if any(rel_path.startswith(ex) for ex in EXTRA_EXCLUDE):
                continue
            if INCLUDE_ONLY and not any(
                rel_path.startswith(inc) for inc, _ in INCLUDE_ONLY
            ):
                continue

            if is_binary(abs_path):
                continue

            collected.append(rel_path)
    return sorted(collected)


# ── Main ──────────────────────────────────────────────────────────────────────


def bundle():
    spec = load_gitignore()
    files = collect_files(spec)
    git_status = get_git_status()
    git_changed = get_git_changed_files()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:

        # Header
        out.write(f"# Code Context\n")
        out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        # Directory tree
        out.write("## Project Structure\n```\n")
        for root, dirs, fs in os.walk("."):
            dirs[:] = [
                d
                for d in dirs
                if d not in IGNORED_DIRS and not spec.match_file(os.path.join(root, d))
            ]
            level = root.replace(".", "").count(os.sep)
            indent = "    " * level
            if root != ".":
                out.write(f"{indent}{os.path.basename(root)}/\n")
            for f in sorted(fs):
                rel = os.path.relpath(os.path.join(root, f), ".")
                if f not in IGNORED_FILES and not spec.match_file(rel):
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
        if INCLUDE_ONLY:
            out.write("## Source Files\n\n")

            for rel_path in files:
                matched_opts = next(
                    (opts for inc, opts in INCLUDE_ONLY if rel_path.startswith(inc)),
                    None,
                )
                if matched_opts is None:
                    continue

                changed = " ⚡ (modified)" if rel_path in git_changed else ""
                ext = rel_path.rsplit(".", 1)[-1] if "." in rel_path else ""
                out.write(f"### `{rel_path}`{changed}\n```{ext}\n")
                try:
                    with open(rel_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    if matched_opts.get("strip_comments") and ext == "py":
                        source = strip_python_comments(source)
                    out.write(source)
                except Exception as e:
                    out.write(f"// Error reading: {e}\n")
                out.write("\n```\n\n")

    print(f"✓ {OUTPUT_FILE} — {len(files)} files bundled")
    if INCLUDE_ONLY:
        print(f"  Selective: {INCLUDE_ONLY}")
    if git_changed:
        print(f"  ⚡ {len(git_changed)} files changed since last commit")


if __name__ == "__main__":
    bundle()
