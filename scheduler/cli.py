# -*- coding: utf-8 -*-
"""
Command-line interface for the scheduler.

Usage:
    python -m scheduler list [--tag TAG] [--env ENV]
    python -m scheduler run TASK_ID [--tag TAG] [--dry-run] [--env ENV]
    python -m scheduler status TASK_ID [--env ENV]
    python -m scheduler summary [--env ENV]
"""
import argparse
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cmd_list(args):
    """List all registered tasks."""
    from scheduler.loader import load_tasks
    tasks = load_tasks()

    tag = getattr(args, "tag", None)
    if tag:
        tasks = [t for t in tasks if tag in t.get("tags", [])]

    if not tasks:
        print("No tasks found.")
        return 0

    # Print table header
    print(f"{'ID':<30} {'Name':<20} {'Tags':<20} {'Enabled':<8} {'Depends'}")
    print("-" * 100)
    for t in tasks:
        tid = t.get("id", "")
        name = t.get("name", "")
        tags = ", ".join(t.get("tags", []))
        enabled = str(t.get("enabled", True))
        deps = ", ".join(t.get("depends_on", []))
        print(f"{tid:<30} {name:<20} {tags:<20} {enabled:<8} {deps}")
    return 0


def cmd_run(args):
    """Run a task or all tasks."""
    from scheduler.loader import load_tasks
    from scheduler.dag import build_subgraph, filter_by_tag, run_dag
    from scheduler.executor import execute_task

    all_tasks = load_tasks()
    env = getattr(args, "env", None)
    dry_run = getattr(args, "dry_run", False)
    task_id = getattr(args, "task_id", "all")
    tag = getattr(args, "tag", None)

    # Filter by tag if specified
    if tag:
        tasks = filter_by_tag(all_tasks, tag)
    else:
        tasks = all_tasks

    # Filter by task ID if not 'all'
    if task_id != "all":
        tasks = build_subgraph(tasks, [task_id])

    if not tasks:
        print(f"No tasks found (task_id={task_id}, tag={tag})")
        return 1

    print(f"Running {len(tasks)} task(s) (dry_run={dry_run}, env={env})")

    completed = run_dag(
        tasks,
        executor_fn=lambda t, c: execute_task(t, c, dry_run=dry_run, env=env),
        dry_run=dry_run,
    )

    # Print summary
    success = sum(1 for s in completed.values() if s == "success")
    failed = sum(1 for s in completed.values() if s == "failed")
    skipped = sum(1 for s in completed.values() if s == "skipped")
    print(f"\nResults: {success} success, {failed} failed, {skipped} skipped")

    if failed > 0:
        return 1
    return 0


def cmd_status(args):
    """Show recent status of a task."""
    from scheduler.state import recent_runs

    task_id = getattr(args, "task_id", "")
    env = getattr(args, "env", None)

    try:
        runs = recent_runs(task_id, n=10, env=env)
    except Exception as e:
        print(f"Error querying status: {e}")
        return 1

    if not runs:
        print(f"No runs found for task: {task_id}")
        return 0

    print(f"Recent runs for: {task_id} (env={env or 'default'})")
    print(f"{'Started':<22} {'Finished':<22} {'Status':<10} {'Duration':<10} {'Retry':<6} {'Error'}")
    print("-" * 100)
    for r in runs:
        started = str(r.get("started_at", ""))
        finished = str(r.get("finished_at", ""))
        status = str(r.get("status", ""))
        duration = f"{r.get('avg_duration_s', r.get('duration_s', 0))}s"
        retry = str(r.get("retry_count", 0))
        error = str(r.get("error_msg", ""))[:40]
        print(f"{started:<22} {finished:<22} {status:<10} {duration:<10} {retry:<6} {error}")
    return 0


def cmd_summary(args):
    """Show today's execution summary."""
    from scheduler.state import today_summary

    env = getattr(args, "env", None)

    try:
        rows = today_summary(env=env)
    except Exception as e:
        print(f"Error querying summary: {e}")
        return 1

    if not rows:
        print("No tasks executed today.")
        return 0

    print(f"Today's summary (env={env or 'default'}):")
    print(f"{'Task':<30} {'Status':<10} {'Count':<6} {'Avg Duration':<14} {'Last Error'}")
    print("-" * 90)
    for r in rows:
        tid = str(r.get("task_id", ""))
        status = str(r.get("status", ""))
        cnt = str(r.get("cnt", 0))
        avg_dur = f"{r.get('avg_duration_s', 0)}s"
        error = str(r.get("last_error", ""))[:30]
        print(f"{tid:<30} {status:<10} {cnt:<6} {avg_dur:<14} {error}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="scheduler",
        description="myTrader unified task scheduler"
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List registered tasks")
    p_list.add_argument("--tag", help="Filter by tag")
    p_list.add_argument("--env", help="Environment (local/online)")

    # run
    p_run = sub.add_parser("run", help="Run task(s)")
    p_run.add_argument("task_id", help="Task ID or 'all'")
    p_run.add_argument("--tag", help="Filter by tag")
    p_run.add_argument("--dry-run", action="store_true", dest="dry_run", help="Dry run")
    p_run.add_argument("--env", help="Environment (local/online)")

    # status
    p_status = sub.add_parser("status", help="Show task status")
    p_status.add_argument("task_id", help="Task ID")
    p_status.add_argument("--env", help="Environment (local/online)")

    # summary
    p_summary = sub.add_parser("summary", help="Today's execution summary")
    p_summary.add_argument("--env", help="Environment (local/online)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "list": cmd_list,
        "run": cmd_run,
        "status": cmd_status,
        "summary": cmd_summary,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
