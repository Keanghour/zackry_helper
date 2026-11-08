# zackry_cli/commands/deploy.py
#
# zackry d - Docker Deployment Tool
# Creates Dockerfile, .dockerignore (and pip.conf for Python)
# for a FastAPI or a Spring Boot project.

import json
import re
from pathlib import Path

import questionary
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

console = Console()

DEFAULT_TIMEZONE = "Asia/Bangkok"

PYTHON_IMAGES = [
    "python:3.13-slim",
    "python:3.12-slim",
    "python:3.11-slim",
]
CUSTOM_IMAGE = "__custom__"

JAVA_VERSIONS = ["17", "21", "25"]

# Packages that the FastAPI Dockerfile needs in requirements.txt
REQUIRED_PACKAGES = ["gunicorn", "uvicorn-worker"]


class Cancelled(Exception):
    """The user pressed Ctrl+C in a prompt."""


# ============================================================
# Prompt helpers
# ============================================================
def _ask(question):
    answer = question.ask()
    if answer is None:
        raise Cancelled()
    return answer


def ask_text(message, default="", validate=None):
    return _ask(
        questionary.text(message, default=default, validate=validate)
    ).strip()


def regex_validator(pattern, error, allow_empty=False):
    compiled = re.compile(pattern)

    def validate(value):
        value = value.strip()

        if not value and allow_empty:
            return True

        return True if compiled.fullmatch(value) else error

    return validate


def number_validator(minimum, maximum, error):
    def validate(value):
        value = value.strip()

        if value.isdigit() and minimum <= int(value) <= maximum:
            return True

        return error

    return validate


validate_timezone = regex_validator(
    r"[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*",
    "Use a timezone name like Asia/Bangkok or UTC",
)
validate_module = regex_validator(
    r"[A-Za-z_][\w.]*:[A-Za-z_]\w*",
    "Use the form module:variable, for example app.main:app",
)
validate_url = regex_validator(
    r"https?://\S+",
    "Must start with http:// or https:// (or leave empty)",
    allow_empty=True,
)
validate_hosts = regex_validator(
    r"[\w.\-:]+(\s+[\w.\-:]+)*",
    "Use host names separated by spaces (or leave empty)",
    allow_empty=True,
)
validate_image = regex_validator(
    r"[\w.\-/:@]+",
    "Use an image name like registry.company.com/python:3.12",
)
validate_path = regex_validator(
    r"/[\w\-./]*",
    "Must start with / and have no spaces",
)
validate_port = number_validator(1, 65535, "Enter a port from 1 to 65535")
validate_workers = number_validator(1, 64, "Enter a number from 1 to 64")


def validate_java_opts(value):
    if '"' in value or "\\" in value:
        return 'Do not use " or \\ characters'
    return True


# ============================================================
# File helpers
# ============================================================
def write_file(path: Path, content: str) -> bool:
    if path.exists() and not _ask(
        questionary.confirm(f"{path} already exists. Overwrite?", default=False)
    ):
        console.print(f"⏭️ [yellow]{path} skipped[/yellow]")
        return False

    path.write_text(content, encoding="utf-8")
    console.print(f"📄 [green]{path} created[/green]")
    return True


def image_name() -> str:
    """Docker image name from the current folder name."""
    name = re.sub(r"[^a-z0-9_.-]+", "-", Path.cwd().name.lower()).strip("-")
    return name or "app"


def requirement_name(line: str) -> str:
    line = line.strip().lower()

    if not line or line.startswith(("#", "-")):
        return ""

    return re.split(r"[<>=!~\[;\s@]", line, maxsplit=1)[0].replace("_", "-")


def check_requirements():
    """Make sure requirements.txt has the packages the Dockerfile needs."""
    req_path = Path("requirements.txt")

    if not req_path.exists():
        console.print(
            "[yellow]⚠️ requirements.txt not found. The Dockerfile needs it, "
            f"with at least: {', '.join(REQUIRED_PACKAGES)}[/yellow]"
        )
        return

    text = req_path.read_text(encoding="utf-8")
    present = {requirement_name(line) for line in text.splitlines()}
    missing = [pkg for pkg in REQUIRED_PACKAGES if pkg not in present]

    if not missing:
        return

    console.print(
        f"[yellow]⚠️ requirements.txt is missing: {', '.join(missing)}[/yellow]"
    )

    if _ask(
        questionary.confirm("Add them to requirements.txt?", default=True)
    ):
        prefix = "" if text.endswith("\n") or not text else "\n"

        with req_path.open("a", encoding="utf-8") as file:
            file.write(prefix + "\n".join(missing) + "\n")

        console.print("[green]✅ requirements.txt updated[/green]")


# ============================================================
# Templates: Python (FastAPI)
# ============================================================
def build_pip_conf(index_url, extra_index_url, trusted_host) -> str:
    lines = [
        "# Used inside the Docker image (copied to /etc/pip.conf)",
        "[global]",
    ]

    if index_url:
        lines.append(f"index-url = {index_url}")
    if extra_index_url:
        lines.append(f"extra-index-url = {extra_index_url}")
    if trusted_host:
        lines.append(f"trusted-host = {trusted_host}")

    return "\n".join(lines) + "\n"


def build_fastapi_dockerfile(cfg) -> str:
    tz = cfg["timezone"]
    port = cfg["port"]
    chown = "--chown=app:app " if cfg["non_root"] else ""

    lines = [
        f"FROM {cfg['base_image']}",
        "",
        "ENV PYTHONUNBUFFERED=1 \\",
        "    PYTHONDONTWRITEBYTECODE=1 \\",
        "    PIP_DISABLE_PIP_VERSION_CHECK=1 \\",
        f"    TZ={tz}",
        "",
        "# Timezone",
        f"RUN echo '{tz}' | tee /etc/timezone && \\",
        f"    ln -sf /usr/share/zoneinfo/{tz} /etc/localtime",
        "",
        "WORKDIR /app",
        "",
    ]

    if cfg["pip_conf"]:
        lines += [
            "# Private pip index settings",
            "COPY pip.conf /etc/",
            "",
        ]

    if cfg["non_root"]:
        lines += [
            "# Run as a normal user, not root",
            "RUN useradd --system --no-create-home --uid 10001 app",
            "",
        ]

    lines += [
        "# Install dependencies first: this layer is reused until requirements.txt changes",
        "COPY requirements.txt .",
        "RUN pip install --no-cache-dir -r requirements.txt",
        "",
        "# Copy the application",
        f"COPY {chown}. .",
        "",
        f"EXPOSE {port}",
    ]

    if cfg["expose_443"] and port != 443:
        lines.append("EXPOSE 443")

    lines.append("")

    if cfg["healthcheck_path"]:
        url = f"http://127.0.0.1:{port}{cfg['healthcheck_path']}"
        lines += [
            "HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \\",
            f"    CMD python -c \"import urllib.request; urllib.request.urlopen('{url}', timeout=3)\"",
            "",
        ]

    if cfg["non_root"]:
        lines += ["USER app", ""]

    command = [
        "gunicorn",
        cfg["app_module"],
        "--workers",
        str(cfg["workers"]),
        "--worker-class",
        "uvicorn_worker.UvicornWorker",
        "--bind",
        f"0.0.0.0:{port}",
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
    ]
    lines.append(f"CMD {json.dumps(command)}")

    return "\n".join(lines) + "\n"


PYTHON_DOCKERIGNORE = """\
.git
.gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
venv/
.venv/

# Secrets: pass them at run time with --env-file instead
.env
keys/

.vscode/
.idea/
.DS_Store
*.log

Dockerfile
.dockerignore
"""


# ============================================================
# Templates: Java (Spring Boot)
# ============================================================
def build_spring_dockerfile(cfg) -> str:
    tz = cfg["timezone"]
    java = cfg["java_version"]
    port = cfg["port"]
    ext = "war" if cfg["packaging"] == "war" else "jar"
    chown = "--chown=spring:spring " if cfg["non_root"] else ""

    if cfg["build_tool"] == "maven":
        build_cmd = "RUN chmod +x mvnw && ./mvnw -q -DskipTests package"
        output_dir = "target"
    else:
        task = "bootWar" if ext == "war" else "bootJar"
        build_cmd = f"RUN chmod +x gradlew && ./gradlew {task} -x test --no-daemon"
        output_dir = "build/libs"

    lines = [
        "# ---- Build stage ----",
        f"FROM eclipse-temurin:{java}-jdk AS build",
        "WORKDIR /app",
        "COPY . .",
        build_cmd,
        "",
        "# ---- Run stage ----",
        f"FROM eclipse-temurin:{java}-jre",
        "",
        f"ENV TZ={tz} \\",
        f"    SERVER_PORT={port} \\",
        f'    JAVA_OPTS="{cfg["java_opts"]}"',
        "",
        "# Timezone",
        f"RUN echo '{tz}' | tee /etc/timezone && \\",
        f"    ln -sf /usr/share/zoneinfo/{tz} /etc/localtime",
        "",
        "WORKDIR /app",
        "",
    ]

    if cfg["non_root"]:
        lines += [
            "# Run as a normal user, not root",
            "RUN useradd --system --no-create-home --uid 10001 spring",
            "",
        ]

    lines += [
        f"COPY {chown}--from=build /app/{output_dir}/*.{ext} app.{ext}",
        "",
        f"EXPOSE {port}",
        "",
    ]

    if cfg["non_root"]:
        lines += ["USER spring", ""]

    lines.append(
        f'ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.{ext}"]'
    )

    return "\n".join(lines) + "\n"


SPRING_DOCKERIGNORE = """\
.git
.gitignore
target/
build/
.gradle/
.idea/
.vscode/
*.iml
.DS_Store

# Secrets: pass them at run time with --env-file instead
.env
keys/

Dockerfile
.dockerignore
"""


# ============================================================
# Flow: Python (FastAPI)
# ============================================================
def deploy_fastapi():
    console.print(
        Panel(
            "[bold green]FastAPI Docker Setup[/bold green]\n"
            "Creates Dockerfile, .dockerignore and pip.conf",
            border_style="green",
        )
    )

    base_image = _ask(
        questionary.select(
            "Base image:",
            choices=[
                *[questionary.Choice(image, image) for image in PYTHON_IMAGES],
                questionary.Choice("Custom image (private registry)", CUSTOM_IMAGE),
            ],
            default=PYTHON_IMAGES[1],
        )
    )

    custom = base_image == CUSTOM_IMAGE

    if custom:
        base_image = ask_text(
            "Image name:",
            validate=validate_image,
        )

    timezone = ask_text("Timezone:", DEFAULT_TIMEZONE, validate_timezone)
    app_module = ask_text("App module:", "app.main:app", validate_module)
    port = int(ask_text("Port:", "80", validate_port))
    expose_443 = _ask(questionary.confirm("Also EXPOSE 443 (HTTPS)?", default=True))
    workers = int(ask_text("Gunicorn workers:", "4", validate_workers))

    healthcheck_path = ""
    if _ask(questionary.confirm("Add a HEALTHCHECK?", default=True)):
        healthcheck_path = ask_text(
            "Health check path:", "/api/v1/health", validate_path
        )

    # ---- private pip index ----
    pip_conf = None

    if _ask(questionary.confirm("Use a private pip index (pip.conf)?", default=True)):
        console.print("[dim]Leave a value empty to skip it[/dim]")

        index_url = ask_text("index-url:", "", validate_url)
        extra_index_url = ask_text("extra-index-url:", "", validate_url)
        trusted_host = ask_text("trusted-host:", "", validate_hosts)

        if index_url or extra_index_url or trusted_host:
            pip_conf = build_pip_conf(index_url, extra_index_url, trusted_host)

            if re.search(r"://[^/@\s]+:[^/@\s]+@", pip_conf):
                console.print(
                    "[yellow]⚠️ pip.conf contains a username and password. "
                    "Do not commit it to git.[/yellow]"
                )
        else:
            console.print("[yellow]No values entered, pip.conf skipped.[/yellow]")

    # Ports below 1024 need root, and we can only add a user to Debian images
    non_root = port >= 1024 and not custom

    if port < 1024:
        console.print(
            "[dim]Port below 1024: the container runs as root. Use a port like "
            "8000 behind nginx to run as a normal user.[/dim]"
        )

    cfg = {
        "base_image": base_image,
        "timezone": timezone,
        "app_module": app_module,
        "port": port,
        "expose_443": expose_443,
        "workers": workers,
        "healthcheck_path": healthcheck_path,
        "pip_conf": pip_conf is not None,
        "non_root": non_root,
    }

    console.print()
    write_file(Path("Dockerfile"), build_fastapi_dockerfile(cfg))
    write_file(Path(".dockerignore"), PYTHON_DOCKERIGNORE)

    if pip_conf is not None:
        write_file(Path("pip.conf"), pip_conf)

    check_requirements()

    name = image_name()
    env_flag = "--env-file .env " if Path(".env").exists() else ""

    console.print("\n💡 [bold cyan]Next steps:[/bold cyan]")
    console.print(f"  1. docker build -t {name} .")
    console.print(
        f"  2. docker run -d --name {name} -p {port}:{port} {env_flag}{name}"
    )

    if Path(".env").exists():
        console.print(
            "\n[dim].env is not copied into the image (see .dockerignore). "
            "It is passed with --env-file.[/dim]"
        )

    console.print()


# ============================================================
# Flow: Java (Spring Boot)
# ============================================================
def deploy_spring():
    console.print(
        Panel(
            "[bold green]Spring Boot Docker Setup[/bold green]\n"
            "Creates Dockerfile and .dockerignore",
            border_style="green",
        )
    )

    # Guess the build tool from the files in this folder
    has_gradle = Path("build.gradle").exists() or Path("build.gradle.kts").exists()

    build_tool = _ask(
        questionary.select(
            "Build tool:",
            choices=[
                questionary.Choice("Maven", "maven"),
                questionary.Choice("Gradle", "gradle"),
            ],
            default="gradle" if has_gradle else "maven",
        )
    )

    java_version = _ask(
        questionary.select(
            "Java version:",
            choices=[questionary.Choice(v, v) for v in JAVA_VERSIONS],
            default="21",
        )
    )

    packaging = _ask(
        questionary.select(
            "Packaging:",
            choices=[
                questionary.Choice("Jar", "jar"),
                questionary.Choice("War", "war"),
            ],
            default="jar",
        )
    )

    timezone = ask_text("Timezone:", DEFAULT_TIMEZONE, validate_timezone)
    port = int(ask_text("Port:", "8080", validate_port))
    java_opts = ask_text(
        "JVM options:",
        "-XX:MaxRAMPercentage=75.0",
        validate_java_opts,
    )

    non_root = port >= 1024

    if not non_root:
        console.print(
            "[dim]Port below 1024: the container runs as root. Use a port like "
            "8080 behind nginx to run as a normal user.[/dim]"
        )

    cfg = {
        "build_tool": build_tool,
        "java_version": java_version,
        "packaging": packaging,
        "timezone": timezone,
        "port": port,
        "java_opts": java_opts,
        "non_root": non_root,
    }

    console.print()
    write_file(Path("Dockerfile"), build_spring_dockerfile(cfg))
    write_file(Path(".dockerignore"), SPRING_DOCKERIGNORE)

    name = image_name()
    env_flag = "--env-file .env " if Path(".env").exists() else ""

    console.print("\n💡 [bold cyan]Next steps:[/bold cyan]")
    console.print(f"  1. docker build -t {name} .")
    console.print(
        f"  2. docker run -d --name {name} -p {port}:{port} {env_flag}{name}"
    )
    console.print()


# ============================================================
# Main menu:  zackry d
# ============================================================
def deploy_tool():
    console.print("\n🚀 [bold magenta]Docker Deployment Tool[/bold magenta]\n")

    try:
        project_type = _ask(
            questionary.select(
                "Select project type:",
                choices=[
                    questionary.Choice("🐍 Python - FastAPI", "fastapi"),
                    questionary.Choice("☕ Java - Spring Boot", "spring"),
                ],
            )
        )

        if project_type == "fastapi":
            deploy_fastapi()
        elif project_type == "spring":
            deploy_spring()

    except Cancelled:
        console.print("\n[yellow]Cancelled.[/yellow]")