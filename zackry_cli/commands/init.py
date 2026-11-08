# zackry_cli/commands/init.py

import questionary
from rich.console import Console
from rich.panel import Panel

console = Console()


def init_project():
    """zackry i - ask which kind of project to create, then run that flow."""

    console.print(
        Panel(
            "[bold green]ZACKRY Project Initializer[/bold green]\n"
            "Choose the type of project you want to create",
            border_style="green",
        )
    )

    project_type = questionary.select(
        "Select project type:",
        choices=[
            questionary.Choice(
                title="🐍 Python - FastAPI",
                value="fastapi",
            ),
            questionary.Choice(
                title="☕ Java - Spring Boot",
                value="spring",
            ),
        ],
    ).ask()

    # User pressed Ctrl+C
    if project_type is None:
        console.print("[yellow]Project initialization cancelled.[/yellow]")
        return

    # Imported only when chosen, so one flow never breaks the other
    if project_type == "fastapi":
        from zackry_cli.commands.init_fastapi import init_fastapi_project
        init_fastapi_project()
    elif project_type == "spring":
        from zackry_cli.commands.init_spring import init_spring_project
        init_spring_project()