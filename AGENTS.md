# Repository Guidelines

## Project Structure & Module Organization

This repository stores local Codex/Claude-style skills.

## Build, Test, and Development Commands

No build step is required. Run the script directly with the explicit interpreter documented in `SKILL.md`:

```bash
/opt/miniconda3/bin/python3 alphaxiv/scripts/alphaxiv.py search "attention is all you need" --limit 5
/opt/miniconda3/bin/python3 alphaxiv/scripts/alphaxiv.py summary 1706.03762
```

Check syntax before committing script changes:

```bash
/opt/miniconda3/bin/python3 -m py_compile alphaxiv/scripts/alphaxiv.py
```

## Coding Style & Naming Conventions

Use concise, standard Python with 4-space indentation. Keep command handlers named `cmd_<command>` and register matching argparse subcommands in `main()`. Prefer explicit helper functions for shared API, formatting, and parsing logic. Keep skill documentation in Markdown and use short command examples that can be copied directly.

## Commit & Pull Request Guidelines

The repository currently has only an initial commit, so no detailed commit convention exists. Use clear imperative commit messages, for example `Add AlphaXiv markdown lookup command`. Pull requests should describe the skill behavior changed, list manual verification commands, and note whether network access or `ALPHAXIV_TOKEN` is required. Do not include `.DS_Store`, cache files, or temporary outputs from `alphaxiv/tmp/`.

When a Codex task finishes a discrete change, create a checkpoint commit with `git commit -m "checkpoint: after codex task1_name"`. Before starting a new change, if there are new modifications since the previous checkpoint commit, create `git commit -m "checkpoint: before codex task2_name"` so review and rollback points stay clear.

## Security & Configuration Tips

Never commit tokens or local shell configuration. Keep `ALPHAXIV_TOKEN` in the environment or `~/.zshrc`. Prefer public, unauthenticated endpoints when a task does not require chat or account-specific data.
