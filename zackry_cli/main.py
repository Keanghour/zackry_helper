# zackry_cli/main.py

from importlib.metadata import PackageNotFoundError, version as pkg_version

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

app = typer.Typer(
    help="ZACKRY CLI 🚀",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


# ----------------------------
# Helper Functions
# ----------------------------
def get_cli_version() -> str:
    """Read the version of the installed package (works inside a .whl)."""
    try:
        return pkg_version("zackry-cli")
    except PackageNotFoundError:
        # Running from source without installing
        from zackry_cli import __version__
        return __version__


def print_banner_info():
    ver = get_cli_version()

    content = Text.from_markup(
        f"""
[yellow]Version:[/yellow] [bold yellow]{ver}[/bold yellow]

📣 Created by: [bold cyan]Hour Zackry[/bold cyan]

🔗 GitHub:     [green]https://github.com/Keanghour[/green]
🔗 LinkedIn:   [green]https://www.linkedin.com/in/pho-keanghour-27133b21b/[/green]
💬 Telegram:   [green]https://t.me/phokeanghour[/green]
""".strip()
    )

    panel = Panel(
        content,
        title="[bold green]ZACKRY CLI[/bold green]",
        border_style="bright_magenta",
        padding=(1, 2),
        expand=False,
    )

    console.print(panel)


# ----------------------------
# Callback: `zackry`, `zackry --version`
# ----------------------------
@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version_flag: bool = typer.Option(
        False, "--version", "-v", help="Show CLI version"
    ),
):
    """
    ZACKRY CLI: project helper tools
    """
    if version_flag:
        print_banner_info()
        raise typer.Exit()

    # `zackry` with no command -> show banner + help
    if ctx.invoked_subcommand is None:
        print_banner_info()
        typer.echo(ctx.get_help())
        raise typer.Exit()


# ----------------------------
# CLI Commands
# ----------------------------
# Names that open the helper screen:  zackry helper | help | h
# (plain `zackry` with no command shows it too, see main_callback)
HELPER_MAIN = "helper"
HELPER_ALIASES = ["help", "h"]


def helper(ctx: typer.Context):
    """zackry helper - Show banner and all available commands (also: help, h)"""
    print_banner_info()
    typer.echo(ctx.parent.get_help())


# The main name is listed in the help; the aliases work but stay hidden
app.command(HELPER_MAIN)(helper)

for _alias in HELPER_ALIASES:
    app.command(_alias, hidden=True)(helper)


@app.command("i")
def i():
    """zackry i - Initialize a new project (FastAPI or Spring Boot) ⚡"""
    # Imported here so `zackry helper` still works even if
    # something inside the init flow is missing or slow to load.
    from zackry_cli.commands.init import init_project

    init_project()


@app.command("d")
def d():
    """zackry d - Docker Deployment Tool (FastAPI / Spring Boot) 🚀"""
    from zackry_cli.commands.deploy import deploy_tool

    deploy_tool()


@app.command("e")
def e():
    """zackry e - Encryption Tools (AES / RSA) 🔐"""
    from zackry_cli.commands.encrypt import encrypt_menu

    encrypt_menu()


TEST_MAIN = "test"
TEST_ALIASES = ["perf"]


def test_cmd():
    """zackry test - API Performance & Security Testing Tool (also: perf)"""
    from zackry_cli.commands.test import test_tool

    test_tool()


app.command(TEST_MAIN)(test_cmd)

for _alias in TEST_ALIASES:
    app.command(_alias, hidden=True)(test_cmd)


@app.command("version")
def version():
    """zackry version - Show CLI version"""
    print_banner_info()


# ----------------------------
# Entry Point
# ----------------------------
def main():
    app()


if __name__ == "__main__":
    main()