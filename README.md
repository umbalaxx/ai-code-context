# AI Code Context

This is a tool that generates a markdown file with the current state of the project. It is used to provide context to AI models when they are working on a project.

## Installation

Clone the repository and install the tool:

```bash
uv tool install .
```

## Usage

To initialize a new project with a config file, run:

```bash
code-context init
```

Then go into the project directory and run:

```bash
code-context
```

## Configuration

The script is configured in `src/ai_code_context/cx_script.py`.

Your project level configuration lives in `.code-context/config.toml`.

You can modify the following settings:

- `OUTPUT_FILE`: The name of the output markdown file
- `INCLUDE_README`: Whether to include the README.md file (default to False)
- `TREE_DEPTH`: The depth of the tree to include
- `INCLUDE_ONLY`: Specific files or directories to include (default to an empty list)
    - `PATH`: The path to the file or directory to include
    - `MODE`: The mode to use when including the file or directory "full" (default) | "symbols" (symbol index only, no source block)
    - `SYMBOLS`: The symbols to include from the file or directory
    - `LINE_NUMBERS`: Line numbers to include ([start, end], e.g. [1, 10])
    - `STRIP_COMMENTS`: Whether to strip comments from the file

**Example config.toml**
```toml
output = "code_context.md"
include_readme = false
# tree_depth = 3 # Uncomment to set tree depth

# Add files/dirs to include.
# mode: "full" (default) | "symbols" (symbol index only, no source block)
# symbols: list of symbol names — show only those symbols' source
# line_numbers: [start, end] — show only that line range (1-indexed, inclusive)
# strip_comments: strip Python # comments from source

[[include]]
path = "src"
strip_comments = false

[[include]]
path = "utils/util.py"
line_numbers = [1, 50]
strip_comments = false
```
