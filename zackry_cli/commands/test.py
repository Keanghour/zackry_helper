# zackry_cli/commands/test.py
#
# zackry test - API Performance & Security Testing Tool
#
# Phase 1: project structure + API configuration.
# Everything else in the menu is wired up but shows "coming in a later
# phase" until that phase is built, so the menu shape stays final.

import json

import questionary
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console()


class Cancelled(Exception):
    """The user pressed Ctrl+C in a prompt."""


def _ask(question):
    answer = question.ask()
    if answer is None:
        raise Cancelled()
    return answer


# ============================================================
# Entry point - checks the optional extra is installed
# ============================================================
def test_tool():
    try:
        import pydantic as _pydantic  # noqa: F401
        import dotenv as _dotenv  # noqa: F401
    except ImportError:
        console.print(
            "\n[red]❌ zackry test needs extra packages that are not installed.[/red]\n"
            "Install them with:\n\n"
            "  [bold]pip install \"zackry-cli[test]\"[/bold]\n"
        )
        return

    from zackry_cli.testtool import storage

    try:
        apis = storage.load_apis()
    except storage.ConfigError as error:
        console.print(f"[red]❌ {escape(str(error))}[/red]")
        return

    console.print(
        Panel(
            "[bold green]API Performance & Security Testing Tool[/bold green]\n"
            "Test APIs you configure here. Nothing is sent until you choose a test.",
            border_style="green",
        )
    )

    try:
        main_menu(apis)
    except Cancelled:
        console.print("\n[yellow]Cancelled.[/yellow]")


# ============================================================
# Main menu
# ============================================================
MENU_ITEMS = [
    ("configure", "Configure APIs"),
    ("test_fastapi", "Test FastAPI"),
    ("test_spring", "Test Spring Boot"),
    ("test_both", "Test Both APIs"),
    ("performance", "Performance Testing"),
    ("security", "Security Testing"),
    ("run_all", "Run All Tests"),
    ("view_results", "View Previous Results"),
    ("export", "Export Report"),
    ("exit", "Exit"),
]

# Phase this item is planned for, shown in the "not built yet" message
PLANNED_PHASE = {
    "test_fastapi": "Phase 3",
    "test_spring": "Phase 3",
    "test_both": "Phase 3",
    "performance": "Phase 3",
    "security": "Phase 4",
    "run_all": "Phase 3/4",
    "view_results": "Phase 5",
    "export": "Phase 6",
}


def main_menu(apis):
    from zackry_cli.testtool import storage

    while True:
        console.print()
        choice = _ask(
            questionary.select(
                "API TESTING TOOL",
                choices=[
                    questionary.Choice(label, value=key)
                    for key, label in MENU_ITEMS
                ],
            )
        )

        if choice == "exit":
            console.print("[cyan]Goodbye![/cyan]")
            return

        if choice == "configure":
            apis = configure_apis_menu(apis)
            continue

        phase = PLANNED_PHASE.get(choice, "a later phase")
        console.print(
            f"[yellow]⏳ '{dict(MENU_ITEMS)[choice]}' is coming in {phase}. "
            "Configure your APIs now so it's ready to use.[/yellow]"
        )

        # Keep .env.example in sync even if the user only browses the menu
        storage.write_env_example(apis)


# ============================================================
# Configure APIs
# ============================================================
def configure_apis_menu(apis):
    from zackry_cli.testtool import storage

    while True:
        console.print()
        choice = _ask(
            questionary.select(
                "Configure APIs",
                choices=[
                    questionary.Choice("List APIs", "list"),
                    questionary.Choice("Add API", "add"),
                    questionary.Choice("Edit API", "edit"),
                    questionary.Choice("Delete API", "delete"),
                    questionary.Choice("Back", "back"),
                ],
            )
        )

        if choice == "back":
            return apis

        if choice == "list":
            list_apis(apis)

        elif choice == "add":
            apis = add_api(apis)

        elif choice == "edit":
            apis = edit_api(apis)

        elif choice == "delete":
            apis = delete_api(apis)


def list_apis(apis):
    if not apis:
        console.print("[yellow]No APIs configured yet.[/yellow]")
        return

    table = Table(title="Configured APIs")
    table.add_column("Name")
    table.add_column("Base URL")
    table.add_column("Auth")
    table.add_column("Endpoints")

    for name, api in apis.items():
        table.add_row(
            name,
            api.base_url,
            api.auth.type.value,
            str(len(api.endpoints)),
        )

    console.print(table)


# ------------------------------------------------------------
# Add / Edit API
# ------------------------------------------------------------
def ask_auth_config(default=None):
    """Prompt for an AuthConfig. Returns a dict (not yet validated)."""
    from zackry_cli.testtool.config import AuthType

    current = default.type.value if default else "none"

    auth_type = _ask(
        questionary.select(
            "Authentication type:",
            choices=[
                questionary.Choice("None", AuthType.NONE.value),
                questionary.Choice("Bearer token (Authorization: Bearer ...)", AuthType.BEARER.value),
                questionary.Choice("API key header", AuthType.API_KEY.value),
            ],
            default=current,
        )
    )

    data = {"type": auth_type}

    if auth_type == AuthType.BEARER.value:
        data["token_env"] = _ask(
            questionary.text(
                "Env var that holds the token (not the token itself):",
                default=(default.token_env if default else "API_TOKEN"),
            )
        ).strip()

    elif auth_type == AuthType.API_KEY.value:
        data["api_key_header"] = _ask(
            questionary.text(
                "Header name for the API key:",
                default=(default.api_key_header if default else "X-API-Key"),
            )
        ).strip()
        data["api_key_env"] = _ask(
            questionary.text(
                "Env var that holds the API key (not the key itself):",
                default=(default.api_key_env if default else "API_KEY"),
            )
        ).strip()

    return data


def ask_endpoint(existing_names, api_default_auth):
    """Prompt for one EndpointConfig. Returns a dict (not yet validated)."""
    name = _ask(questionary.text("Endpoint name:")).strip()

    method = _ask(
        questionary.select(
            "HTTP method:",
            choices=["GET", "POST", "PUT", "PATCH", "DELETE"],
            default="GET",
        )
    )

    path = _ask(questionary.text("Path (starts with /):", default="/")).strip()

    headers = {}
    if _ask(questionary.confirm("Add custom headers?", default=False)):
        while True:
            key = _ask(questionary.text("Header name (leave empty to stop):")).strip()
            if not key:
                break
            value = _ask(questionary.text(f"Value for {key}:")).strip()
            headers[key] = value

    body = None
    if method in ("POST", "PUT", "PATCH") and _ask(
        questionary.confirm("Add a JSON request body?", default=False)
    ):
        while True:
            raw = _ask(questionary.text('Body as JSON (e.g. {"a": 1}):'))
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("the top level must be a JSON object: { ... }")
                break
            except (json.JSONDecodeError, ValueError) as error:
                console.print(f"[red]❌ Invalid JSON: {escape(str(error))}[/red]")

    auth = None
    if _ask(
        questionary.confirm(
            f"Override auth for this endpoint? (default: {api_default_auth.type.value})",
            default=False,
        )
    ):
        auth = ask_auth_config(default=api_default_auth)

    data = {"name": name, "method": method, "path": path, "headers": headers}
    if body is not None:
        data["body"] = body
    if auth is not None:
        data["auth"] = auth

    return data


def add_api(apis):
    from zackry_cli.testtool.config import APIConfig

    name = _ask(questionary.text("API name:")).strip()

    if name in apis:
        console.print(f"[red]❌ '{escape(name)}' already exists. Use Edit instead.[/red]")
        return apis

    base_url = _ask(
        questionary.text("Base URL (e.g. https://api.example.com):")
    ).strip()
    timeout = _ask(questionary.text("Default timeout in seconds:", default="10")).strip()

    console.print("[cyan]Default authentication for this API:[/cyan]")
    auth_data = ask_auth_config()

    endpoints = []
    while _ask(
        questionary.confirm(
            f"Add an endpoint to '{name}'?" if not endpoints else "Add another endpoint?",
            default=True,
        )
    ):
        from zackry_cli.testtool.config import AuthConfig

        endpoint_data = ask_endpoint(
            [e["name"] for e in endpoints],
            AuthConfig(**auth_data),
        )
        endpoints.append(endpoint_data)

    try:
        api = APIConfig(
            name=name,
            base_url=base_url,
            timeout=float(timeout),
            auth=auth_data,
            endpoints=endpoints,
        )
    except (ValidationError, ValueError) as error:
        console.print(f"[red]❌ Could not save '{escape(name)}':[/red]\n{escape(str(error))}")
        return apis

    apis = {**apis, name: api}
    _save(apis)
    console.print(f"[green]✅ '{name}' saved with {len(api.endpoints)} endpoint(s)[/green]")
    return apis


def edit_api(apis):
    if not apis:
        console.print("[yellow]No APIs configured yet.[/yellow]")
        return apis

    name = _ask(
        questionary.select("Edit which API?", choices=list(apis.keys()))
    )
    api = apis[name]

    action = _ask(
        questionary.select(
            f"Editing '{name}'",
            choices=[
                questionary.Choice("Change base URL / timeout / auth", "basics"),
                questionary.Choice("Add an endpoint", "add_endpoint"),
                questionary.Choice("Remove an endpoint", "remove_endpoint"),
                questionary.Choice("Cancel", "cancel"),
            ],
        )
    )

    if action == "cancel":
        return apis

    data = api.model_dump()

    if action == "basics":
        data["base_url"] = _ask(
            questionary.text("Base URL:", default=api.base_url)
        ).strip()
        data["timeout"] = float(
            _ask(questionary.text("Default timeout in seconds:", default=str(api.timeout)))
        )
        console.print("[cyan]Default authentication for this API:[/cyan]")
        data["auth"] = ask_auth_config(default=api.auth)

    elif action == "add_endpoint":
        endpoint_data = ask_endpoint([e.name for e in api.endpoints], api.auth)
        data["endpoints"].append(endpoint_data)

    elif action == "remove_endpoint":
        if not api.endpoints:
            console.print("[yellow]No endpoints to remove.[/yellow]")
            return apis

        target = _ask(
            questionary.select(
                "Remove which endpoint?",
                choices=[e.name for e in api.endpoints],
            )
        )
        data["endpoints"] = [e for e in data["endpoints"] if e["name"] != target]

    from zackry_cli.testtool.config import APIConfig

    try:
        updated = APIConfig.model_validate(data)
    except (ValidationError, ValueError) as error:
        console.print(f"[red]❌ Could not save '{escape(name)}':[/red]\n{escape(str(error))}")
        return apis

    apis = {**apis, name: updated}
    _save(apis)
    console.print(f"[green]✅ '{name}' updated[/green]")
    return apis


def delete_api(apis):
    if not apis:
        console.print("[yellow]No APIs configured yet.[/yellow]")
        return apis

    name = _ask(
        questionary.select("Delete which API?", choices=list(apis.keys()))
    )

    if not _ask(
        questionary.confirm(f"Delete '{name}'? This cannot be undone.", default=False)
    ):
        console.print("[yellow]Cancelled.[/yellow]")
        return apis

    apis = {k: v for k, v in apis.items() if k != name}
    _save(apis)
    console.print(f"[green]✅ '{name}' deleted[/green]")
    return apis


def _save(apis):
    from zackry_cli.testtool import storage

    storage.save_apis(apis)