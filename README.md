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
- `INCLUDE_ONLY`: Specific files or directories to include (default to an empty list)
    - `PATH`: The path to the file or directory to include
    - `STRIP_COMMENTS`: Whether to strip comments from the file

**Example config.toml**
```toml
output = "code_context.md"
include_readme = false

[[include]]
path = "src"
strip_comments = false

[[include]]
path = "utils/util.py"
strip_comments = false
```
