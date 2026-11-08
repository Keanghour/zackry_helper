# zackry_cli/commands/init_spring.py

from pathlib import Path
from io import BytesIO
import re
import zipfile

import requests
import questionary

from rich.console import Console
from rich.panel import Panel

from zackry_cli.templates import docker as docker_templates

console = Console()

INITIALIZR_URL = "https://start.spring.io"
USER_AGENT = "ZACKRY-CLI/1.0"


# -------------------------
# Metadata helpers
# -------------------------
def get_initializr_metadata():
    console.print("[cyan]Fetching Spring Initializr options...[/cyan]")

    response = requests.get(
        INITIALIZR_URL,
        headers={
            "Accept": "application/vnd.initializr.v2.3+json",
            "User-Agent": USER_AGENT,
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()


def get_options(metadata, key):
    section = metadata.get(key, {})
    values = section.get("values", [])

    return [
        {
            "id": item["id"],
            "name": item.get("name", item["id"]),
            "default": item.get("default", False),
        }
        for item in values
        if isinstance(item, dict) and item.get("id")
    ]


def select_option(message, options, labels=None):
    if not options:
        raise ValueError(f"No available options for: {message}")

    choices = []

    for item in options:
        value = item["id"]
        label = (
            labels.get(value, item["name"])
            if labels
            else item["name"]
        )

        choices.append(
            questionary.Choice(
                title=label,
                value=value,
            )
        )

    # Pre-select the default value that Spring Initializr recommends
    default = next(
        (item["id"] for item in options if item.get("default")),
        None,
    )

    return questionary.select(
        message,
        choices=choices,
        default=default,
    ).ask()


# -------------------------
# Dependencies (loaded live from start.spring.io)
# -------------------------
def get_compatible_dependency_ids(boot_version):
    """
    Ask Spring Initializr which dependencies work with the chosen
    Spring Boot version. Returns None if it can not be loaded
    (then all dependencies are shown).
    """
    try:
        response = requests.get(
            f"{INITIALIZR_URL}/dependencies",
            params={"bootVersion": boot_version},
            headers={
                "Accept": "application/vnd.initializr.v2.1+json",
                "User-Agent": USER_AGENT,
            },
            timeout=20,
        )
        response.raise_for_status()
        ids = set(response.json().get("dependencies", {}).keys())
        return ids or None
    except (requests.RequestException, ValueError):
        return None


def get_dependency_choices(metadata, compatible_ids=None):
    """Build the checkbox list from the live Initializr metadata."""
    groups = metadata.get("dependencies", {}).get("values", [])
    choices = []

    for group in groups:
        group_name = group.get("name", "Other")

        for dep in group.get("values", []):
            dep_id = dep.get("id")

            if not dep_id:
                continue

            if compatible_ids and dep_id not in compatible_ids:
                continue

            choices.append(
                questionary.Choice(
                    title=f"{group_name} › {dep.get('name', dep_id)}",
                    value=dep_id,
                    description=dep.get("description", ""),
                )
            )

    return choices


# -------------------------
# Project metadata
# -------------------------
def get_project_metadata():
    group = questionary.text(
        "Group:",
        default="com.example",
    ).ask()

    if group is None:
        return None

    artifact = questionary.text(
        "Artifact:",
        default="demo",
    ).ask()

    if artifact is None:
        return None

    name = questionary.text(
        "Name:",
        default=artifact,
    ).ask()

    if name is None:
        return None

    default_package = f"{group}.{artifact.replace('-', '_')}"

    package_name = questionary.text(
        "Package name:",
        default=default_package,
    ).ask()

    if package_name is None:
        return None

    if not re.fullmatch(
        r"[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)*",
        group,
    ):
        console.print("[red]Invalid Group name.[/red]")
        return None

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", artifact):
        console.print("[red]Invalid Artifact name.[/red]")
        return None

    if not re.fullmatch(
        r"[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)*",
        package_name,
    ):
        console.print("[red]Invalid Package name.[/red]")
        return None

    return {
        "groupId": group,
        "artifactId": artifact,
        "name": name,
        "packageName": package_name,
    }


# -------------------------
# Safely extract ZIP
# -------------------------
def extract_project(zip_content, destination):
    destination = destination.resolve()

    with zipfile.ZipFile(BytesIO(zip_content)) as archive:
        for item in archive.infolist():

            target = (destination / item.filename).resolve()

            if not target.is_relative_to(destination):
                raise ValueError("Unsafe file path in generated archive")

            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(item) as source:
                    target.write_bytes(source.read())

                # Keep the executable bit (needed for ./mvnw and ./gradlew)
                mode = (item.external_attr >> 16) & 0o777
                if mode:
                    target.chmod(mode)


# -------------------------
# Docker files for the Spring project
# -------------------------
def write_docker_files(destination, project_type, java_version, packaging):
    """Write Dockerfile and .dockerignore into the new Spring Boot project."""
    template = (
        docker_templates.SPRING_DOCKERFILE_MAVEN
        if project_type == "maven-project"
        else docker_templates.SPRING_DOCKERFILE_GRADLE
    )

    extension = "war" if packaging == "war" else "jar"

    dockerfile = (
        template
        .replace("{JAVA_VERSION}", str(java_version))
        .replace("{EXT}", extension)
        .replace("{GRADLE_TASK}", "bootWar" if extension == "war" else "bootJar")
    )

    created = []

    for name, content in (
        ("Dockerfile", dockerfile),
        (".dockerignore", docker_templates.SPRING_DOCKERIGNORE),
    ):
        target = destination / name

        if target.exists():
            console.print(f"⚠️ [yellow]{name} already exists — skipped[/yellow]")
            continue

        target.write_text(content, encoding="utf-8")
        console.print(f"📄 [green]{name} created[/green]")
        created.append(name)

    return created


# -------------------------
# Initialize Spring project
# -------------------------
def init_spring_project():

    console.print(
        Panel(
            "[bold green]Spring Boot Project Generator[/bold green]\n"
            "Powered by Spring Initializr",
            border_style="green",
        )
    )

    try:
        # -------------------------
        # Get live metadata
        # -------------------------
        metadata = get_initializr_metadata()

        # -------------------------
        # Project type
        # -------------------------
        project_labels = {
            "maven-project": "Maven",
            "gradle-project": "Gradle - Groovy",
            "gradle-project-kotlin": "Gradle - Kotlin",
        }

        project_options = [
            item for item in get_options(metadata, "type")
            if item["id"] in project_labels
        ]

        project_type = select_option(
            "Project:",
            project_options,
            project_labels,
        )

        if project_type is None:
            return

        # -------------------------
        # Language
        # -------------------------
        language = select_option(
            "Language:",
            get_options(metadata, "language"),
        )

        if language is None:
            return

        # -------------------------
        # Spring Boot version
        # -------------------------
        boot_options = get_options(metadata, "bootVersion")

        boot_version = select_option(
            "Spring Boot:",
            boot_options,
        )

        if boot_version is None:
            return

        # -------------------------
        # Project metadata
        # -------------------------
        project_info = get_project_metadata()

        if project_info is None:
            return

        # -------------------------
        # Packaging
        # -------------------------
        packaging = select_option(
            "Packaging:",
            get_options(metadata, "packaging"),
        )

        if packaging is None:
            return

        # -------------------------
        # Configuration format
        # -------------------------
        config_format = select_option(
            "Configuration:",
            get_options(metadata, "configurationFileFormat"),
        )

        if config_format is None:
            return

        # -------------------------
        # Java version
        # -------------------------
        java_version = select_option(
            "Java:",
            get_options(metadata, "javaVersion"),
        )

        if java_version is None:
            return

        # -------------------------
        # Dependencies (loaded live from start.spring.io)
        # -------------------------
        console.print(
            f"[cyan]Loading dependencies for Spring Boot {boot_version}...[/cyan]"
        )

        compatible_ids = get_compatible_dependency_ids(boot_version)
        dependency_choices = get_dependency_choices(metadata, compatible_ids)

        dependencies = []

        if dependency_choices:
            console.print(
                "[dim]Type to search · Space to select · Enter to confirm[/dim]"
            )

            dependencies = questionary.checkbox(
                "Select dependencies:",
                choices=dependency_choices,
                use_search_filter=True,
                use_jk_keys=False,
            ).ask()

            if dependencies is None:
                return
        else:
            console.print(
                "[yellow]Dependency list not available. "
                "Continuing without dependencies.[/yellow]"
            )

        # -------------------------
        # Docker support
        # -------------------------
        add_docker = questionary.confirm(
            "Add Dockerfile?",
            default=True,
        ).ask()

        if add_docker is None:
            return

        # -------------------------
        # Build API parameters
        # -------------------------
        params = {
            "type": project_type,
            "language": language,
            "bootVersion": boot_version,
            "packaging": packaging,
            "javaVersion": java_version,
            "configurationFileFormat": config_format,
            **project_info,
        }

        if dependencies:
            params["dependencies"] = ",".join(dependencies)

        # -------------------------
        # Project destination
        # -------------------------
        destination = Path(project_info["artifactId"])

        if destination.exists():
            overwrite = questionary.confirm(
                f"Directory '{destination}' already exists. Continue?",
                default=False,
            ).ask()

            if not overwrite:
                console.print("[yellow]Generation cancelled.[/yellow]")
                return

            if any(destination.iterdir()):
                console.print(
                    "[red]Destination must be empty to avoid "
                    "overwriting existing files.[/red]"
                )
                return

        destination.mkdir(parents=True, exist_ok=True)

        # -------------------------
        # Generate project ZIP
        # -------------------------
        console.print(
            "\n[cyan]Generating Spring Boot project...[/cyan]"
        )

        response = requests.get(
            f"{INITIALIZR_URL}/starter.zip",
            params=params,
            headers={
                "User-Agent": USER_AGENT,
            },
            timeout=60,
        )

        if not response.ok:
            console.print(
                f"[red]Spring Initializr error: "
                f"{response.status_code}[/red]"
            )
            console.print(response.text[:2000])
            return

        if not zipfile.is_zipfile(BytesIO(response.content)):
            console.print(
                "[red]Invalid project archive returned by Initializr.[/red]"
            )
            return

        # -------------------------
        # Extract project
        # -------------------------
        extract_project(response.content, destination)

        if add_docker:
            write_docker_files(
                destination,
                project_type,
                java_version,
                packaging,
            )

        # -------------------------
        # Success
        # -------------------------
        console.print("\n" + "=" * 45)

        console.print(
            Panel(
                f"[bold green]Project created successfully![/bold green]\n\n"
                f"Name: {project_info['name']}\n"
                f"Group: {project_info['groupId']}\n"
                f"Artifact: {project_info['artifactId']}\n"
                f"Package: {project_info['packageName']}\n"
                f"Project: {project_labels[project_type]}\n"
                f"Language: {language}\n"
                f"Spring Boot: {boot_version}\n"
                f"Packaging: {packaging}\n"
                f"Configuration: {config_format}\n"
                f"Java: {java_version}\n"
                f"Dependencies: {', '.join(dependencies) if dependencies else 'None'}\n"
                f"Docker: {'Dockerfile added' if add_docker else 'No'}",
                title="ZACKRY CLI",
                border_style="green",
            )
        )

        console.print("\n💡 [bold cyan]Next steps:[/bold cyan]")

        console.print(f"  1. cd {destination}")

        if project_type == "maven-project":
            console.print("  2. ./mvnw spring-boot:run")
        else:
            console.print("  2. ./gradlew bootRun")

        if add_docker:
            image = project_info["artifactId"].lower()
            console.print(f"  3. docker build -t {image} .")
            console.print(f"  4. docker run -p 8080:8080 {image}")

        console.print("\n🎉 Happy coding!\n")

    except requests.RequestException as error:
        console.print(
            f"\n[red]Unable to connect to Spring Initializr:[/red] {error}"
        )

    except (ValueError, KeyError, zipfile.BadZipFile) as error:
        console.print(f"\n[red]Project generation failed:[/red] {error}")