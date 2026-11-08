# zackry_cli/commands/encrypt.py

import base64
import os
from pathlib import Path

import questionary
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

console = Console()

ENV_PATH = Path(".env")

# AES: one secret key stored in .env
AES_KEY_NAME = "AES_KEY"

# RSA: key pair stored as PEM files
KEYS_DIR = Path("keys")
RSA_PRIVATE_FILE = KEYS_DIR / "private_key.pem"
RSA_PUBLIC_FILE = KEYS_DIR / "public_key.pem"

# Lines in .env that hold keys and must never be encrypted
# ("KEY" is the old name used by the previous Fernet tool)
SKIP_NAMES = {"KEY", AES_KEY_NAME}


# ============================================================
# Shared helpers
# ============================================================
def spinner_task(message: str, func, *args, **kwargs):
    """Show a spinner while a task is running."""
    with console.status(f"[cyan]{message}...", spinner="dots"):
        return func(*args, **kwargs)


def mask(value: str) -> str:
    """Show only the first 2 characters of a secret."""
    if len(value) <= 2:
        return "***"
    return value[:2] + "*" * min(len(value) - 2, 8)


def split_env_line(line: str):
    """Return (name, value) for a KEY=VALUE line, or (None, None)."""
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        return None, None

    name, value = line.split("=", 1)
    return name.strip(), value.strip()


def read_env_lines():
    if not ENV_PATH.exists():
        console.print("[red]❌ .env file not found![/red]")
        return None

    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def write_env_lines(lines):
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ask_value(message: str):
    value = questionary.text(message).ask()

    if not value:
        console.print("[yellow]⚠️ No value entered[/yellow]")
        return None

    return value


# ============================================================
# Encrypt / decrypt the whole .env (shared by AES and RSA)
# ============================================================
def encrypt_env(encrypt_fn, is_encrypted_fn):
    lines = read_env_lines()
    if lines is None:
        return

    targets = []
    already = []

    for index, line in enumerate(lines):
        name, value = split_env_line(line)

        if name is None or name in SKIP_NAMES or not value:
            continue

        if is_encrypted_fn(value):
            already.append(name)
        else:
            targets.append((index, name, value))

    if already:
        console.print(
            f"[yellow]⏭️ Already encrypted, skipped: {', '.join(already)}[/yellow]"
        )

    if not targets:
        console.print("[yellow]⚠️ No variables to encrypt[/yellow]")
        return

    console.print("[cyan]Variables to encrypt:[/cyan]")
    for _, name, value in targets:
        console.print(f"  {name} = {escape(mask(value))}")

    if not questionary.confirm("Encrypt these variables?", default=True).ask():
        console.print("[yellow]Operation cancelled.[/yellow]")
        return

    new_lines = list(lines)

    for index, name, value in targets:
        try:
            new_lines[index] = f"{name}={encrypt_fn(value)}"
        except ValueError as error:
            console.print(f"[red]❌ {name}: {escape(str(error))}[/red]")
            console.print("[yellow]Operation cancelled, .env not modified[/yellow]")
            return

    console.print("\nPreview of encrypted .env:")
    for index, _, _ in targets:
        console.print(f"  {escape(new_lines[index])}")

    if questionary.confirm("Save changes to .env?", default=True).ask():
        spinner_task("Saving .env", write_env_lines, new_lines)
        console.print("[green]✅ .env encrypted in-place[/green]")
    else:
        console.print("[yellow]Operation cancelled, .env not modified[/yellow]")


def decrypt_env(decrypt_fn):
    lines = read_env_lines()
    if lines is None:
        return

    targets = []
    failed = []

    for index, line in enumerate(lines):
        name, value = split_env_line(line)

        if name is None or name in SKIP_NAMES or not value:
            continue

        try:
            targets.append((index, name, decrypt_fn(value)))
        except Exception:
            failed.append(name)

    if failed:
        console.print(
            "[yellow]⏭️ Not encrypted (or wrong key), left unchanged: "
            f"{', '.join(failed)}[/yellow]"
        )

    if not targets:
        console.print("[yellow]⚠️ No variables to decrypt[/yellow]")
        return

    new_lines = list(lines)
    for index, name, plain in targets:
        new_lines[index] = f"{name}={plain}"

    console.print("[cyan]Preview of decrypted .env:[/cyan]")
    for index, _, _ in targets:
        console.print(f"  {escape(new_lines[index])}")

    if questionary.confirm("Save decrypted values to .env?", default=True).ask():
        spinner_task("Saving .env", write_env_lines, new_lines)
        console.print("[green]✅ .env decrypted in-place[/green]")
    else:
        console.print("[yellow]Operation cancelled, .env not modified[/yellow]")


# ============================================================
# AES-256-GCM  (symmetric: one secret key)
# ============================================================
def aes_encrypt(key: bytes, text: str) -> str:
    """Returns base64( nonce + ciphertext + tag )."""
    nonce = os.urandom(12)
    cipher = AESGCM(key).encrypt(nonce, text.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + cipher).decode("utf-8")


def aes_decrypt(key: bytes, token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode("utf-8"))
    nonce, cipher = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, cipher, None).decode("utf-8")


def aes_load_key():
    if not ENV_PATH.exists():
        console.print("[red]❌ .env file not found! Generate a key first.[/red]")
        return None

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        name, value = split_env_line(line)

        if name == AES_KEY_NAME:
            try:
                key = base64.urlsafe_b64decode(value)
            except ValueError:
                key = b""

            if len(key) != 32:
                console.print(
                    f"[red]❌ {AES_KEY_NAME} in .env is not a valid 256-bit key. "
                    "Generate a new key.[/red]"
                )
                return None

            return key

    console.print(
        f"[red]❌ {AES_KEY_NAME} not found in .env! Generate a key first.[/red]"
    )
    return None


def aes_generate_key():
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    has_key = any(split_env_line(l)[0] == AES_KEY_NAME for l in lines)

    if has_key and not questionary.confirm(
        f"{AES_KEY_NAME} already exists in .env. Replace it? "
        "(values encrypted with the old key can no longer be decrypted)",
        default=False,
    ).ask():
        console.print("[yellow]Operation cancelled, key not changed.[/yellow]")
        return

    key = AESGCM.generate_key(bit_length=256)
    encoded = base64.urlsafe_b64encode(key).decode("utf-8")

    lines = [l for l in lines if split_env_line(l)[0] != AES_KEY_NAME]
    write_env_lines([f"{AES_KEY_NAME}={encoded}"] + lines)

    console.print(f"[green]✅ Generated AES-256 key:[/green] {encoded}")
    console.print(f"[green]✅ Key saved in .env as {AES_KEY_NAME}[/green]")
    console.print("[yellow]⚠️ Keep .env private and never commit it to git.[/yellow]")


def aes_encrypt_value():
    key = aes_load_key()
    if key is None:
        return

    value = ask_value("Enter the value to encrypt")
    if value is None:
        return

    token = spinner_task("Encrypting value", aes_encrypt, key, value)
    console.print(f"[green]✅ Encrypted value:[/green] {token}")


def aes_decrypt_value():
    key = aes_load_key()
    if key is None:
        return

    value = ask_value("Enter the value to decrypt")
    if value is None:
        return

    try:
        plain = spinner_task("Decrypting value", aes_decrypt, key, value)
        console.print(f"[green]✅ Decrypted value:[/green] {escape(plain)}")
    except Exception:
        console.print("[red]❌ Failed to decrypt. Is the value and key correct?[/red]")


def aes_encrypt_env():
    key = aes_load_key()
    if key is None:
        return

    def is_encrypted(value: str) -> bool:
        try:
            aes_decrypt(key, value)
            return True
        except Exception:
            return False

    encrypt_env(lambda v: aes_encrypt(key, v), is_encrypted)


def aes_decrypt_env():
    key = aes_load_key()
    if key is None:
        return

    decrypt_env(lambda v: aes_decrypt(key, v))


def aes_menu():
    console.print("\n🔑 [bold cyan]AES-256-GCM[/bold cyan] (one secret key)\n")

    choice = questionary.select(
        "Choose an action",
        choices=[
            questionary.Choice("Generate Key", "generate"),
            questionary.Choice("Encrypt Value", "encrypt"),
            questionary.Choice("Decrypt Value", "decrypt"),
            questionary.Choice("Encrypt Entire .env File", "encrypt_env"),
            questionary.Choice("Decrypt Entire .env File", "decrypt_env"),
        ],
    ).ask()

    actions = {
        "generate": aes_generate_key,
        "encrypt": aes_encrypt_value,
        "decrypt": aes_decrypt_value,
        "encrypt_env": aes_encrypt_env,
        "decrypt_env": aes_decrypt_env,
    }

    if choice in actions:
        actions[choice]()


# ============================================================
# RSA  (asymmetric: public key encrypts, private key decrypts)
# ============================================================
def _oaep():
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


def rsa_encrypt(public_key, text: str) -> str:
    data = text.encode("utf-8")
    limit = public_key.key_size // 8 - 2 * hashes.SHA256().digest_size - 2

    if len(data) > limit:
        raise ValueError(
            f"value is {len(data)} bytes, but this RSA key can encrypt "
            f"at most {limit} bytes. Use a bigger key or use AES."
        )

    cipher = public_key.encrypt(data, _oaep())
    return base64.urlsafe_b64encode(cipher).decode("utf-8")


def rsa_decrypt(private_key, token: str) -> str:
    cipher = base64.urlsafe_b64decode(token.encode("utf-8"))
    return private_key.decrypt(cipher, _oaep()).decode("utf-8")


def write_private_file(path: Path, data: bytes):
    """Write a file that only the owner can read."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(data)
    path.chmod(0o600)


def find_key_file(default: Path, label: str):
    """Use the default key file, or ask for its path."""
    if default.exists():
        return default

    console.print(f"[yellow]⚠️ {label} not found at {default}[/yellow]")
    answer = questionary.path(f"Path to {label}:").ask()

    if not answer:
        return None

    path = Path(answer).expanduser()

    if not path.is_file():
        console.print(f"[red]❌ File not found: {escape(str(path))}[/red]")
        return None

    return path


def rsa_load_public_key():
    path = find_key_file(RSA_PUBLIC_FILE, "public key")
    if path is None:
        return None

    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except ValueError:
        console.print("[red]❌ This is not a valid PEM public key.[/red]")
        return None

    if not isinstance(key, rsa.RSAPublicKey):
        console.print("[red]❌ This is not an RSA public key.[/red]")
        return None

    return key


def rsa_load_private_key():
    path = find_key_file(RSA_PRIVATE_FILE, "private key")
    if path is None:
        return None

    data = path.read_bytes()

    try:
        try:
            key = serialization.load_pem_private_key(data, password=None)
        except TypeError:
            # The key is protected with a passphrase
            passphrase = questionary.password("Private key passphrase:").ask()
            if not passphrase:
                return None
            key = serialization.load_pem_private_key(
                data, password=passphrase.encode("utf-8")
            )
    except ValueError:
        console.print(
            "[red]❌ Could not read the private key (wrong passphrase or "
            "invalid file).[/red]"
        )
        return None

    if not isinstance(key, rsa.RSAPrivateKey):
        console.print("[red]❌ This is not an RSA private key.[/red]")
        return None

    return key


def offer_gitignore():
    """Offer to add keys/ to .gitignore so the private key is never committed."""
    gitignore = Path(".gitignore")

    if not gitignore.exists():
        return

    text = gitignore.read_text(encoding="utf-8")

    if any(l.strip() in ("keys/", "keys") for l in text.splitlines()):
        return

    if questionary.confirm("Add keys/ to .gitignore?", default=True).ask():
        with gitignore.open("a", encoding="utf-8") as file:
            prefix = "" if text.endswith("\n") or not text else "\n"
            file.write(f"{prefix}\n# RSA keys\nkeys/\n")
        console.print("[green]✅ keys/ added to .gitignore[/green]")


def rsa_generate_keys():
    if RSA_PRIVATE_FILE.exists() or RSA_PUBLIC_FILE.exists():
        if not questionary.confirm(
            f"Key files already exist in {KEYS_DIR}/. Replace them? "
            "(values encrypted with the old keys can no longer be decrypted)",
            default=False,
        ).ask():
            console.print("[yellow]Operation cancelled, keys not changed.[/yellow]")
            return

    size = questionary.select(
        "Key size",
        choices=[
            questionary.Choice("2048 bits (standard, fast)", 2048),
            questionary.Choice("3072 bits", 3072),
            questionary.Choice("4096 bits (strongest, slower)", 4096),
        ],
        default=2048,
    ).ask()

    if size is None:
        return

    passphrase = questionary.password(
        "Passphrase to protect the private key (leave empty for none):"
    ).ask()

    if passphrase is None:
        return

    private_key = spinner_task(
        f"Generating {size}-bit RSA key pair",
        rsa.generate_private_key,
        public_exponent=65537,
        key_size=size,
    )

    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode("utf-8"))
        if passphrase
        else serialization.NoEncryption()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    KEYS_DIR.mkdir(exist_ok=True)
    write_private_file(RSA_PRIVATE_FILE, private_pem)
    RSA_PUBLIC_FILE.write_bytes(public_pem)

    console.print(f"[green]✅ Private key:[/green] {RSA_PRIVATE_FILE}")
    console.print(f"[green]✅ Public key: [/green] {RSA_PUBLIC_FILE}")
    console.print(
        "[yellow]⚠️ Keep the private key secret and never commit it to git. "
        "The public key can be shared.[/yellow]"
    )

    offer_gitignore()


def rsa_encrypt_value():
    public_key = rsa_load_public_key()
    if public_key is None:
        return

    value = ask_value("Enter the value to encrypt")
    if value is None:
        return

    try:
        token = spinner_task("Encrypting value", rsa_encrypt, public_key, value)
    except ValueError as error:
        console.print(f"[red]❌ {escape(str(error))}[/red]")
        return

    console.print(f"[green]✅ Encrypted value:[/green] {token}")


def rsa_decrypt_value():
    private_key = rsa_load_private_key()
    if private_key is None:
        return

    value = ask_value("Enter the value to decrypt")
    if value is None:
        return

    try:
        plain = spinner_task("Decrypting value", rsa_decrypt, private_key, value)
        console.print(f"[green]✅ Decrypted value:[/green] {escape(plain)}")
    except Exception:
        console.print(
            "[red]❌ Failed to decrypt. Is the value correct and is this "
            "the matching private key?[/red]"
        )


def rsa_encrypt_env():
    public_key = rsa_load_public_key()
    if public_key is None:
        return

    key_bytes = public_key.key_size // 8

    def is_encrypted(value: str) -> bool:
        # An RSA ciphertext is always exactly as long as the key
        try:
            return len(base64.urlsafe_b64decode(value.encode("utf-8"))) == key_bytes
        except ValueError:
            return False

    encrypt_env(lambda v: rsa_encrypt(public_key, v), is_encrypted)


def rsa_decrypt_env():
    private_key = rsa_load_private_key()
    if private_key is None:
        return

    decrypt_env(lambda v: rsa_decrypt(private_key, v))


def rsa_menu():
    console.print("\n🗝️ [bold cyan]RSA[/bold cyan] (public key + private key)\n")

    choice = questionary.select(
        "Choose an action",
        choices=[
            questionary.Choice("Generate Key Pair", "generate"),
            questionary.Choice("Encrypt Value (public key)", "encrypt"),
            questionary.Choice("Decrypt Value (private key)", "decrypt"),
            questionary.Choice("Encrypt Entire .env File", "encrypt_env"),
            questionary.Choice("Decrypt Entire .env File", "decrypt_env"),
        ],
    ).ask()

    actions = {
        "generate": rsa_generate_keys,
        "encrypt": rsa_encrypt_value,
        "decrypt": rsa_decrypt_value,
        "encrypt_env": rsa_encrypt_env,
        "decrypt_env": rsa_decrypt_env,
    }

    if choice in actions:
        actions[choice]()


# ============================================================
# Main menu:  zackry e
# ============================================================
def encrypt_menu():
    console.print("\n🔐 [bold cyan]Encryption Tools[/bold cyan]\n")

    style = questionary.select(
        "Choose encryption style",
        choices=[
            questionary.Choice("AES-256-GCM  (one secret key, any length)", "aes"),
            questionary.Choice("RSA  (public key + private key, short values)", "rsa"),
        ],
    ).ask()

    if style == "aes":
        aes_menu()
    elif style == "rsa":
        rsa_menu()


# ============================================================
# Guide panel
# ============================================================
def show_encrypt_guide():
    console.print(
        Panel.fit(
            "💡 Encryption Guide\n"
            "• AES-256-GCM → one secret key (AES_KEY in .env), fast, any length\n"
            "• RSA → keys/public_key.pem encrypts, keys/private_key.pem decrypts\n"
            "• RSA can only encrypt short values (about 190 bytes for 2048 bits)\n"
            "• Encrypt/Decrypt Entire .env → in-place with preview\n"
            "\nCreated by: Hour Zackry",
            title="Guide",
            style="yellow",
        )
    )