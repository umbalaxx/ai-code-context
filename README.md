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
