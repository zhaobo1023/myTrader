#!/usr/bin/env bash
# preflight.sh — myTrader 提 MR/合并前的确定性检查编排
#
# 设计原则（来自 Kun Chen firstmate「脚本做结构、agent 做语义」）：
#   把 CLAUDE.md「代码规范 [CRITICAL]」+ 收尾检查里【确定性、可脚本化】的步骤编排成一条命令，
#   一次跑完、带证据、可复现，agent 不必逐条手动跑、不烧 token。
#   语义步骤（diff 每行可追溯、涉资金逻辑的判断、code-review 拍板）不在本脚本内，仍由 agent 做。
#
# 用法：
#   bash scripts/preflight.sh            # 全部（后端 + 前端）
#   bash scripts/preflight.sh --backend  # 只后端
#   bash scripts/preflight.sh --frontend # 只前端
#   bash scripts/preflight.sh --quiet    # 只输出汇总+失败项（省 token，供 agent）
#   bash scripts/preflight.sh --all      # ruff 查全量而非只查本次改动
#
# 特性：遇错不中断，跑完统一汇总。退出码 0=全绿，1=有 error。
# 软检查（环境缺依赖时提示而非失败）：pytest 收集、后端 import 健康。
# 涉资金逻辑/migration 等语义判断脚本不代劳，见 CLAUDE.md 异步沟通与决策分级。

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCOPE="all"; QUIET=0; ALL=0
for a in "$@"; do
  case "$a" in
    --backend) SCOPE="backend" ;;
    --frontend) SCOPE="frontend" ;;
    --quiet) QUIET=1 ;;
    --all) ALL=1 ;;
    *) echo "未知参数: $a（支持 --backend/--frontend/--quiet/--all）" >&2; exit 2 ;;
  esac
done

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python"
WEB="$ROOT/web"

PASS=0; FAIL=0; SKIP=0
FAILED_STEPS=""

run_step() {
  name="$1"; shift
  [ "$QUIET" -eq 0 ] && printf '\n▶ %s\n' "$name"
  out="$("$@" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    PASS=$((PASS+1)); [ "$QUIET" -eq 0 ] && echo "  ✅ 通过"
  else
    FAIL=$((FAIL+1)); FAILED_STEPS="$FAILED_STEPS  ❌ $name (exit $rc)\n"
    echo "  ❌ $name 失败 (exit $rc)"
    printf '%s\n' "$out" | tail -30 | sed 's/^/     /'
  fi
}

# 软检查：依赖缺失则跳过并提示，不计失败
skip_note() {
  SKIP=$((SKIP+1))
  [ "$QUIET" -eq 0 ] && printf '\n▶ %s\n  ⏭ 跳过：%s\n' "$1" "$2"
}

# 本次改动涉及的 .py 文件 = 未提交的工作区改动（staged + unstaged）。
# 注意：myTrader 本地直接提交到 main（不走 feature 分支/MR），故不能用 origin/main...HEAD
# 那会把本地领先远端的几十个 commit 全算成"本次改动"，误报存量。工作区 diff 才是当前任务真正碰的。
changed_py() {
  { git diff --name-only 2>/dev/null; git diff --name-only --cached 2>/dev/null; } \
    | grep -E '\.py$' | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done
}

# ---------- 后端 ----------
if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "backend" ]; then
  # emoji（暂存区）
  run_step "emoji 检查(暂存区)" "$PY" scripts/check_no_emoji.py
  # myTrader 专属代码规则（暂存区）：禁裸 getenv / SQL 占位符 / 枚举 key .value —— CLAUDE.md CRITICAL 的自动化
  run_step "myTrader 代码规则(暂存区)" "$PY" scripts/check_code_rules.py
  # ruff：默认只查本次改动文件（对齐只查改动纪律）；--all 查全量
  if command -v ruff >/dev/null 2>&1; then
    if [ "$ALL" -eq 1 ]; then
      run_step "后端 ruff(全量)" ruff check .
    else
      files="$(changed_py)"
      if [ -n "$files" ]; then run_step "后端 ruff(本次改动)" ruff check $files
      else [ "$QUIET" -eq 0 ] && printf '\n▶ 后端 ruff(本次改动)\n  ⏭ 无改动的 .py 文件，跳过\n'; fi
    fi
  else
    skip_note "后端 ruff" "未找到 ruff"
  fi
  # 后端测试收集：
  #   - venv 未装 pytest → 软跳过
  #   - 全量 tests/ 有存量收集欠账（缺 redis/sentence_transformers 等依赖、测试与代码不同步），
  #     不适合当硬门槛，会天天误报。故默认只收集【本次改动的 .py 对应的测试文件】；
  #     无改动则跳过。--all 时才跑全量（信息性，用于清欠账时看全貌）。
  if "$PY" -c "import pytest" >/dev/null 2>&1; then
    if [ "$ALL" -eq 1 ]; then
      run_step "后端测试收集(全量,含存量欠账)" "$PY" -m pytest tests/ --collect-only -q
    else
      # 找本次改动的 .py 对应的测试文件（test_<名>.py 或路径含该模块名的测试）
      chg="$(changed_py)"
      testfiles=""
      if [ -n "$chg" ]; then
        for f in $chg; do
          stem="$(basename "$f" .py)"
          match="$(git ls-files 'tests/**test*.py' 2>/dev/null | grep -iE "test_${stem}\.py|${stem}.*test|test.*${stem}" || true)"
          [ -n "$match" ] && testfiles="$testfiles $match"
        done
        testfiles="$(printf '%s\n' $testfiles | sort -u | tr '\n' ' ')"
      fi
      if [ -n "$(echo "$testfiles" | tr -d ' ')" ]; then
        run_step "后端测试收集(本次改动相关)" "$PY" -m pytest $testfiles --collect-only -q
      else
        [ "$QUIET" -eq 0 ] && printf '\n▶ 后端测试收集(本次改动相关)\n  ⏭ 本次无改动或无对应测试文件，跳过（全量欠账另见 --all）\n'
      fi
    fi
  else
    skip_note "后端测试收集" "当前 venv 未装 pytest（pip install -r requirements-dev.txt 后可启用）"
  fi
fi

# ---------- 前端 ----------
if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "frontend" ]; then
  if [ -d "$WEB" ] && [ -d "$WEB/node_modules" ]; then
    # 类型检查（package.json 无 type-check script，直接 tsc --noEmit）
    run_step "前端 type-check(tsc)" bash -c "cd '$WEB' && npx tsc --noEmit"
    # lint
    run_step "前端 lint(eslint)" bash -c "cd '$WEB' && npm run lint --silent"
  elif [ -d "$WEB" ]; then
    skip_note "前端检查" "web/node_modules 未安装（cd web && npm install 后可启用）"
  fi
fi

# ---------- 汇总 ----------
echo ""
echo "════════════════════════════════════════"
echo "preflight 汇总：通过 $PASS · 失败 $FAIL · 跳过 $SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf "失败步骤：\n"; printf "$FAILED_STEPS"
  echo ""
  echo "⚠️ 上述为确定性检查失败项。修复后重跑本脚本。"
  echo "   剩余语义步骤（脚本不代劳）：diff 每行可追溯 · 涉资金逻辑/migration 判断 · /code-review 拍板 · 提 MR 与部署问询"
  exit 1
else
  echo "✅ 所有确定性检查通过（跳过 $SKIP 项为环境缺依赖，非失败）。"
  echo "   下一步（语义步骤，agent 做）：git diff 逐行自查 → 涉资金逻辑复核 → /code-review → 提 MR（部署 Prod 绝不自动）"
  exit 0
fi
