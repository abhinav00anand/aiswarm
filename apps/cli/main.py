"""
Zymis CLI — interact with the orchestrator from the command line.

Commands:
  run     — submit a task and stream its progress
  status  — show status of all active tasks
  cancel  — cancel a task by ID
  review  — show review results for a task
  providers — list configured LLM providers
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from typing import Any

from aiswarm.security.auth import APIKeyValidator
from aiswarm.security.audit import get_audit_ledger

app = typer.Typer(
    name="zymis",
    help="Zymis — Lightweight multi-agent orchestration framework",
    rich_markup_mode="rich",
)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)


def _load_env() -> None:
    """Load .env file if present."""
    env_file = Path(".env")
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)


_load_env()


@app.command()
def run(
    title: str = typer.Argument(..., help="Task title"),
    description: str = typer.Option("", "--desc", "-d", help="Task description"),
    target: list[str] = typer.Option([], "--file", "-f", help="Target file(s)"),
    language: str = typer.Option("python", "--lang", "-l", help="Target language"),
    priority: str = typer.Option("NORMAL", "--priority", "-p", help="CRITICAL|HIGH|NORMAL|LOW"),
    max_retries: int = typer.Option(5, "--retries", help="Max retry attempts"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for completion"),
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="Zymis or Provider API Key"),
    adapter_url: str | None = typer.Option(
        None, "--adapter-url", help="OpenAI-compatible adapter URL"
    ),
    provider: str | None = typer.Option(
        None, "--provider", help="Preferred provider (e.g. zephyr, openai)"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Target model (e.g. llama3:8b)"),
    no_ollama: bool = typer.Option(False, "--no-ollama", help="Disable Ollama auto-provisioning"),
    notebook: bool = typer.Option(False, "--notebook", help="Run in lightweight notebook mode"),
) -> None:
    """Submit a task and optionally wait for it to complete."""
    _load_env()
    if provider:
        os.environ["ZYMIS_PREFERRED_PROVIDER"] = provider
        if provider == "zephyr" and model:
            os.environ["ZEPHYR_SELECTED_MODEL"] = model
    elif model:
        if os.getenv("ZEPHYR_API_KEY") or os.getenv("ZEPHYR_API_URL"):
            os.environ["ZEPHYR_SELECTED_MODEL"] = model
    if adapter_url:
        os.environ["OPENAI_API_ADAPTER_URL"] = adapter_url
    if no_ollama:
        os.environ["ZYMIS_NO_OLLAMA"] = "1"
    if notebook:
        os.environ["ZYMIS_NOTEBOOK_MODE"] = "1"

    APIKeyValidator.enforce_startup_auth(api_key)
    asyncio.run(
        _run_task(
            title=title,
            description=description or title,
            target_files=list(target),
            language=language,
            priority=priority,
            max_retries=max_retries,
            wait_for_completion=wait,
            api_key=api_key,
        )
    )


async def _run_task(
    title: str,
    description: str,
    target_files: list[str],
    language: str,
    priority: str,
    max_retries: int,
    wait_for_completion: bool,
    api_key: str | None = None,
) -> None:
    from aiswarm.bootstrap.startup import build_orchestrator
    from aiswarm.schemas.task import Task, TaskPriority

    console.print(
        Panel.fit(
            f"[bold green]Submitting task:[/bold green] {title}",
            border_style="green",
        )
    )

    orc, lifecycle = build_orchestrator(repo_root=".", api_key=api_key)
    await lifecycle.startup()

    task = Task(
        title=title,
        description=description,
        target_files=target_files,
        target_language=language,
        priority=TaskPriority(priority),
        max_retries=max_retries,
    )

    submitted = await orc.submit_task(task)
    console.print(f"[cyan]Task ID:[/cyan] {submitted.task_id}")

    if not wait_for_completion:
        console.print("[yellow]Task submitted. Use 'zymis status' to check progress.[/yellow]")
        await lifecycle.shutdown()
        return

    # Poll for completion
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        prog_task = progress.add_task(f"[cyan]Running pipeline...[/cyan]", total=None)
        last_state = ""

        while True:
            t = await orc.get_task(submitted.task_id)
            if t and t.state.value != last_state:
                last_state = t.state.value
                progress.update(prog_task, description=f"[cyan]State:[/cyan] {last_state}")

            if t and t.state.value in ("MERGED", "REJECTED", "DEADLOCK", "CANCELLED"):
                break

            await asyncio.sleep(2)

    # Show result
    final = await orc.get_task(submitted.task_id)
    if final:
        _display_task_result(final)

    await lifecycle.shutdown()


def _display_task_result(task: Any) -> None:
    state = task.state.value
    color = "green" if state == "MERGED" else "red"

    console.print(
        Panel(
            f"[{color}]Final State: {state}[/{color}]\n"
            f"Retries: {task.retry_count}\n"
            f"Tokens used: {task.total_tokens_used:,}\n"
            f"Estimated cost: ${task.estimated_cost_usd:.4f}\n"
            f"Merged: {task.merged}",
            title=f"Task: {task.title}",
            border_style=color,
        )
    )

    if task.reviews:
        table = Table(title="Critic Reviews")
        table.add_column("Critic", style="cyan")
        table.add_column("Decision", style="bold")
        table.add_column("Score", justify="right")
        table.add_column("Fatal Flaw")
        for r in task.reviews:
            color = "green" if r.decision.value == "APPROVE" else "red"
            table.add_row(
                r.critic_role,
                f"[{color}]{r.decision.value}[/{color}]",
                str(r.score),
                r.fatal_flaw or "—",
            )
        console.print(table)


@app.command()
def providers() -> None:
    """List all configured LLM providers and their availability."""
    _load_env()
    from aiswarm.llm.provider_router import ProviderRouter

    router = ProviderRouter()
    available = router.list_available()
    configured_keys = APIKeyValidator.get_configured_keys()

    console.print(
        f"\n[cyan]Configured API Keys:[/cyan] {', '.join(configured_keys) if configured_keys else 'None'}\n"
    )

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", justify="center")
    for name in [
        "novita",
        "openai",
        "anthropic",
        "gemini",
        "deepseek",
        "bedrock",
        "local",
        "adapter",
    ]:
        status = (
            "[green]✓ Available[/green]" if name in available else "[red]✗ Not configured[/red]"
        )
        table.add_row(name, status)
    console.print(table)


@app.command()
def audit() -> None:
    """View the last 50 audit events."""
    _load_env()

    events = asyncio.run(get_audit_ledger().get_events(limit=50))

    table = Table(title="Audit Ledger (Last 50 Events)")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Event Type", style="magenta")
    table.add_column("Actor", style="blue")
    table.add_column("Task ID", style="green")
    table.add_column("Action", style="yellow")
    table.add_column("Outcome", justify="right")

    for e in events:
        table.add_row(
            str(e.timestamp),
            str(e.event_type),
            str(e.actor),
            str(e.task_id or "-"),
            str(e.action),
            str(e.outcome),
        )
    console.print(table)


@app.command()
def index(
    root: str = typer.Option(".", "--root", "-r", help="Repository root to index"),
) -> None:
    """Index a repository for RAG-powered context selection."""
    _load_env()
    asyncio.run(_index_repo(root))


async def _index_repo(root: str) -> None:
    from aiswarm.rag.repository_indexer import RepositoryIndexer
    from aiswarm.rag.retriever import RAGRetriever

    retriever = RAGRetriever(repo_root=root)
    indexer = RepositoryIndexer(repo_root=root, retriever=retriever)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as p:
        task = p.add_task("[cyan]Indexing repository...[/cyan]", total=None)
        count = await indexer.index_all()
        p.update(task, description=f"[green]Indexed {count} files[/green]")

    console.print(f"[green]✓ Indexed {count} source files into RAG store.[/green]")


@app.command()
def direct(
    prompt: str = typer.Argument(..., help="Prompt to execute directly with model"),
    model: str = typer.Option(
        "gpt-4o", "--model", "-m", help="LLM model (e.g. gpt-4o, claude-3-5-sonnet)"
    ),
    temperature: float = typer.Option(0.7, "--temp", "-t", help="Temperature (0.0 - 1.0)"),
) -> None:
    """Directly execute a prompt through an LLM model with AISwarm security and audit coordination."""
    _load_env()
    from aiswarm.llm.direct_runner import DirectModelCoordinator

    coord = DirectModelCoordinator()
    res = asyncio.run(coord.run_direct(prompt=prompt, model=model, temperature=temperature))
    if res.get("status") == "SUCCESS":
        console.print(
            Panel(
                res.get("content", ""),
                title=f"[bold green]Direct Model Output ({model})[/bold green]",
            )
        )
        console.print(
            f"[dim]Cost: ${res.get('usage', {}).get('cost_usd', 0.0):.4f} | Duration: {res.get('duration_seconds')}s[/dim]"
        )
    else:
        console.print(f"[bold red]Direct Model Failed:[/bold red] {res.get('error')}")


if __name__ == "__main__":
    app()
