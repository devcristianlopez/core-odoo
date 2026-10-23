#!/usr/bin/env bash
# Recreate the OpenCode/Claude/Agent-Skills symlinks after cloning on a system
# where symlinks were not preserved (or after adding a skill).
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for target in .opencode/skills .claude/skills .agents/skills; do
  mkdir -p "$target"
  for dir in skills/*/; do
    name="$(basename "$dir")"
    [ -f "$dir/SKILL.md" ] || continue
    ln -sfn "../../skills/$name" "$target/$name"
  done
done
printf 'Agent skill links refreshed.\n'
