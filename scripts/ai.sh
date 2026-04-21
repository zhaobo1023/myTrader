#!/usr/bin/env bash
# ai.sh - Headless Claude Code scripts for myTrader batch operations
#
# Usage:
#   ./scripts/ai.sh review              # Code review current branch vs main
#   ./scripts/ai.sh sync-model <name>   # Replace LLM model name across all files
#   ./scripts/ai.sh gc                  # Weekly garbage collection (GC)
#   ./scripts/ai.sh debug-prod <desc>   # Production debug runbook
#   ./scripts/ai.sh check               # Quick health check (syntax + emoji)

set -euo pipefail
cd "$(dirname "$0")/.."

CMD="${1:-help}"

case "$CMD" in

  review)
    # Structured code review of current branch vs main
    # Re-fetches diff every time, never uses cache
    echo "[ai.sh] Running code review against main..."
    claude -p "
Run a code review of the current branch against main.
Follow the /review skill in .claude/skills/review/SKILL.md exactly.
Start by running: git diff main...HEAD
" \
      --allowedTools "Bash(git diff *),Bash(git log *),Bash(git status *),Read,Grep,Glob" \
      --permission-mode acceptEdits
    ;;

  sync-model)
    # Replace LLM model name across all Python and YAML files
    MODEL="${2:-}"
    if [ -z "$MODEL" ]; then
      echo "Usage: ./scripts/ai.sh sync-model <new-model-name>"
      echo "Example: ./scripts/ai.sh sync-model qwen3.6-plus"
      exit 1
    fi
    echo "[ai.sh] Syncing model name to: $MODEL"
    claude -p "
Find all references to LLM model names in Python (.py) and YAML (.yaml/.yml) files.
Replace them all with: $MODEL
Rules:
- Only change model name strings (e.g. 'qwen-plus', 'qwen-turbo', 'gpt-4o'), not variable names
- Skip files in .venv/, __pycache__/, output/, node_modules/
- After all edits, run: grep -r '$MODEL' --include='*.py' --include='*.yaml' --include='*.yml' | grep -v '.venv' | head -20
- Show a summary: how many files changed, which files
" \
      --allowedTools "Read,Edit,Grep,Glob,Bash(grep *),Bash(find *)" \
      --permission-mode acceptEdits
    ;;

  gc)
    # Weekly garbage collection - analyze this week's issues and suggest fixes
    echo "[ai.sh] Running weekly GC analysis..."
    git log --since="7 days ago" --oneline | claude -p "
You are running the weekly garbage collection (GC) process.
See docs/claude/weekly_gc.md for the full SOP.

The git log from the last 7 days is provided via stdin.

Steps:
1. Scan the git log for fix/hotfix commits that indicate recurring problems
2. For each problem, classify as A (can be lint rule), B (can be test), or C (document only)
3. Output a prioritized list of the top 3-5 items to address this GC session
4. For each A-class item, suggest the specific change to scripts/check_no_emoji.py or .pre-commit-config.yaml
5. For each B-class item, suggest a test file name and test function stub
6. For each C-class item, suggest which section of CLAUDE.md or docs/claude/ to update

Do NOT make any file changes - output analysis only.
" \
      --allowedTools "Read,Grep,Glob,Bash(git log *),Bash(git diff *)" \
      --permission-mode plan
    ;;

  debug-prod)
    # Production debug runbook
    DESC="${2:-unspecified issue}"
    echo "[ai.sh] Starting production debug runbook for: $DESC"
    claude -p "
Production debug runbook for: $DESC

Follow these steps in order:
1. Check recent git log for changes that could have caused this: git log --oneline -20
2. Search for related error patterns in the codebase: grep -r 'ERROR\|Exception\|CRITICAL' --include='*.py' -l
3. Check config files (.env.example) for relevant environment variables
4. Identify the most likely root cause
5. Propose a minimal fix (do NOT implement yet - output a plan)
6. List any environment variables or external services to verify

When writing scripts to run on remote servers, write them as local files first (do NOT use heredocs).
Output: Root cause hypothesis + fix plan + verification steps
" \
      --allowedTools "Read,Grep,Glob,Bash(git log *),Bash(git diff *),Bash(grep *),Bash(find *)" \
      --permission-mode plan
    ;;

  check)
    # Quick health check: Python syntax + emoji scan
    echo "[ai.sh] Running quick health check..."
    python3 scripts/check_no_emoji.py --all
    echo "[ai.sh] Checking Python syntax..."
    find . -name "*.py" \
      -not -path "./.venv/*" \
      -not -path "./__pycache__/*" \
      -not -path "./output/*" \
      | xargs -I{} python3 -m py_compile {} 2>&1 \
      | grep -v "^$" \
      && echo "[OK] All Python files syntax-clean" \
      || true
    ;;

  help|*)
    echo "Usage: ./scripts/ai.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  review              Code review current branch vs main"
    echo "  sync-model <name>   Replace LLM model name across all files"
    echo "  gc                  Weekly garbage collection analysis"
    echo "  debug-prod <desc>   Production debug runbook (plan only)"
    echo "  check               Quick syntax + emoji health check"
    ;;

esac
