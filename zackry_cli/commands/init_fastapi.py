# zackry_cli/commands/init_fastapi.py

from pathlib import Path
from rich.console import Console
import questionary

from zackry_cli.templates import files, project, docker, db

console = Console()


def init_fastapi_project():
    console.print("\n🎉 [bold green]FastAPI Project Initialization[/bold green]\n")

    # -------------------------
    # Ask DB requirement
    # -------------------------
    need_db = questionary.confirm(
        "Do you need database connection?",
        default=True
    ).ask()

    if need_db is None:
        console.print("[yellow]Project initialization cancelled.[/yellow]")
        return

    console.print(
        "🗄️ Database support: "
        + (
            "[bold green]Enabled[/bold green]"
            if need_db
            else "[yellow]Skipped[/yellow]"
        )
    )

    # -------------------------
    # Project folders
    # -------------------------
    folders = [
        "app",
        "app/core",
        "app/routers",
        "app/services",
        "app/repositories",
        "app/models",
        "app/schemas",
        "app/dependencies",
        "app/middlewares",
        "app/utils",
        "tests",
    ]

    # Database folders (conditional)
    if need_db:
        folders.extend([
            "app/db",
        ])

    # Include custom base directories
    for folder in project.BASE_DIRS:
        if need_db or folder != "app/db":
            if folder not in folders:
                folders.append(folder)

    # -------------------------
    # Python package directories
    # -------------------------
    python_dirs = [
        "app",
        "app/core",
        "app/routers",
        "app/services",
        "app/repositories",
        "app/models",
        "app/schemas",
        "app/dependencies",
        "app/middlewares",
        "app/utils",
        "tests",
    ]

    if need_db:
        python_dirs.append("app/db")

    # -------------------------
    # Create directories
    # -------------------------
    for folder in folders:
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)

        if folder in python_dirs:
            (path / "__init__.py").touch(exist_ok=True)

    console.print(
        "\n🚀 [bold green]Project folders created successfully![/bold green]"
    )

    # -------------------------
    # Base application files
    # -------------------------
    files_map = {

        # Main application
        "app/main.py": files.MAIN_PY,

        # Core
        "app/core/config.py": files.CONFIG_PY,
        "app/core/security.py": files.SECURITY_PY,
        "app/core/logging.py": files.LOGGING_PY,
        "app/core/exceptions.py": files.EXCEPTIONS_PY,

        # Routers
        "app/routers/health.py": files.HEALTH_ROUTER,

        # Services
        "app/services/health_service.py": files.HEALTH_SERVICE,

        # Repositories
        # Add feature-specific repositories when needed.

        # Models
        "app/models/base.py": files.MODELS_BASE,

        # Schemas
        "app/schemas/common.py": files.COMMON_SCHEMA,

        # Dependencies
        "app/dependencies/auth.py": files.AUTH_DEPENDENCY,

        # Middlewares
        "app/middlewares/audit.py": files.MIDDLEWARE_AUDIT_PY,
        "app/middlewares/errors.py": files.MIDDLEWARE_ERRORS_PY,

        # Utils
        "app/utils/encryption.py": files.ENCRYPTION_PY,
        "app/utils/helpers.py": files.HELPERS_PY,
        "app/utils/validators.py": files.VALIDATORS_PY,

        # Tests
        "tests/conftest.py": files.TESTS_CONFTEST,
        "tests/test_health.py": files.TEST_HEALTH,

        # Environment
        ".env": files.ENV_FILE,
        ".env.example": files.ENV_EXAMPLE,
        ".gitignore": files.GITIGNORE,

        # Dependencies
        "requirements.txt": files.REQUIREMENTS,
        "pip.conf": files.PIP_CONF,

        # Deployment
        "Dockerfile": docker.DOCKERFILE,

        # Documentation
        "README.md": files.README,
    }

    # -------------------------
    # Database files (conditional)
    # -------------------------
    if need_db:
        files_map.update({

            "app/db/base.py": db.DB_BASE_PY,
            "app/db/session.py": db.DB_SESSION_PY,

            "app/dependencies/database.py": files.DATABASE_DEPENDENCY,

        })

    # -------------------------
    # Write files safely
    # -------------------------
    created_count = 0
    skipped_count = 0

    for file_path, content in files_map.items():

        dest = Path(file_path)

        if dest.exists():
            console.print(
                f"⚠️ [yellow]{file_path} already exists — skipped[/yellow]"
            )
            skipped_count += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)

        dest.write_text(
            content,
            encoding="utf-8"
        )

        console.print(
            f"📄 [green]{file_path} created[/green]"
        )

        created_count += 1

    # -------------------------
    # Append DB environment variables
    # -------------------------
    if need_db:

        env_path = Path(".env")
        existing_env = env_path.read_text(encoding="utf-8")

        if "POSTGRES_HOST" not in existing_env:

            with env_path.open("a", encoding="utf-8") as env_file:
                env_file.write("\n")
                env_file.write(db.ENV_DB.strip())
                env_file.write("\n")

            console.print(
                "🗄️ [green]Database environment variables added[/green]"
            )

    # -------------------------
    # Append DB packages to requirements.txt
    # -------------------------
    if need_db:

        req_path = Path("requirements.txt")
        existing_req = req_path.read_text(encoding="utf-8")

        if "sqlalchemy" not in existing_req.lower():

            with req_path.open("a", encoding="utf-8") as req_file:
                req_file.write(db.REQUIREMENTS_DB)

            console.print(
                "📦 [green]Database packages added to requirements.txt[/green]"
            )

    # -------------------------
    # Final summary
    # -------------------------
    console.print("\n" + "=" * 45)

    console.print("[bold green]🎉 Project initialized successfully![/bold green]")

    console.print(f"📁 Files created: [green]{created_count}[/green]")
    console.print(f"⏭️ Files skipped: [yellow]{skipped_count}[/yellow]")

    console.print("=" * 45)

    # -------------------------
    # Next steps
    # -------------------------
    console.print("\n💡 [bold cyan]Next steps:[/bold cyan]")

    console.print("  1. Create and activate virtual environment")
    console.print("  2. pip install -r requirements.txt")

    if need_db:
        console.print("  3. Configure database credentials in .env")
        console.print("  4. Start your database")
        console.print("  5. uvicorn app.main:app --reload")
    else:
        console.print("  3. uvicorn app.main:app --reload")

    console.print("\n📚 API Documentation:")
    console.print("  Swagger: http://127.0.0.1:8000/docs")
    console.print("  ReDoc:   http://127.0.0.1:8000/redoc\n")