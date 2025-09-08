"""Development scripts for PlexAniBridge."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from scripts import __file__ as scripts_file

ROOT_DIR = Path(scripts_file).parent.parent.resolve()


class Colors:
    """ANSI color codes for terminal output."""

    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def print_task(message: str) -> None:
    """Print a task message with formatting."""
    print(
        f"{Colors.CYAN}{Colors.BOLD}[DEV]{Colors.END} {Colors.BLUE}{message}"
        f"{Colors.END}"
    )


def print_success(message: str) -> None:
    """Print a success message with formatting."""
    print(
        f"{Colors.CYAN}{Colors.BOLD}[DEV]{Colors.END} {Colors.GREEN}✓ {message}"
        f"{Colors.END}"
    )


def print_error(message: str) -> None:
    """Print an error message with formatting."""
    print(
        f"{Colors.CYAN}{Colors.BOLD}[DEV]{Colors.END} {Colors.RED}✗ {message}"
        f"{Colors.END}"
    )


def print_info(message: str) -> None:
    """Print an info message with formatting."""
    print(
        f"{Colors.CYAN}{Colors.BOLD}[DEV]{Colors.END} {Colors.YELLOW}→ {message}"
        f"{Colors.END}"
    )


def parse_target_args() -> str:
    """Parse command line arguments for target selection."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        default="both",
        choices=["both", "backend", "frontend"],
        help="Target to operate on: both, backend, or frontend",
    )
    args = parser.parse_args()
    return args.target


def build() -> None:
    """Build the application."""
    target = parse_target_args()

    if target == "backend":
        print_info("Backend doesn't require a build step.")
        return

    print_task(f"Building {target}...")

    if target in ("both", "frontend"):
        try:
            print_info("Building frontend...")
            subprocess.run(["pnpm", "build"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend build completed successfully!")
        except subprocess.CalledProcessError:
            print_error("Frontend build failed!")
            raise
        except FileNotFoundError:
            print_error("pnpm not found! Please install pnpm first.")
            raise


def clean() -> None:
    """Clean build artifacts and cache."""
    target = parse_target_args()

    print_task(f"Cleaning {target}...")

    try:
        if target in ("both", "backend"):
            print_info("Cleaning Python cache and build artifacts...")
            subprocess.run(
                [
                    "find",
                    ".",
                    "-type",
                    "d",
                    "-name",
                    "__pycache__",
                    "-print",
                    "-exec",
                    "rm",
                    "-rf",
                    "{}",
                    "+",
                ],
                cwd=ROOT_DIR,
            )
            subprocess.run(["find", ".", "-name", "*.pyc", "-delete"], cwd=ROOT_DIR)
            print_success("Python artifacts cleaned!")

        if target in ("both", "frontend"):
            print_info("Cleaning frontend build artifacts...")
            subprocess.run(["pnpm", "clean"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend artifacts cleaned!")

        print_success(f"{target.capitalize()} cleaning completed!")
    except subprocess.CalledProcessError as e:
        print_error(f"Cleaning failed: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print_error(f"Tool not found: {e}")
        sys.exit(1)


def deps_install() -> None:
    """Install dependencies."""
    target = parse_target_args()

    print_task(f"Installing {target} dependencies...")

    try:
        if target in ("both", "backend"):
            print_info("Installing Python dependencies...")
            subprocess.run(
                ["uv", "sync", "--all-groups", "--all-packages"],
                cwd=ROOT_DIR,
                check=True,
            )
            print_success("Python dependencies installed successfully!")

        if target in ("both", "frontend"):
            print_info("Installing frontend dependencies...")
            subprocess.run(["pnpm", "install"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend dependencies installed successfully!")

    except subprocess.CalledProcessError as e:
        print_error(f"Dependency installation failed: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print_error(f"Tool not found: {e}")
        sys.exit(1)


def deps_upgrade() -> None:
    """Upgrade dependencies."""
    target = parse_target_args()

    print_task(f"Upgrading {target} dependencies...")

    try:
        if target in ("both", "backend"):
            print_info("Upgrading Python dependencies...")
            subprocess.run(
                ["uv", "sync", "--upgrade", "--all-groups", "--all-packages"],
                cwd=ROOT_DIR,
                check=True,
            )
            print_success("Python dependencies upgraded successfully!")

        if target in ("both", "frontend"):
            print_info("Upgrading frontend dependencies...")
            subprocess.run(["pnpm", "update"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend dependencies upgraded successfully!")

    except subprocess.CalledProcessError as e:
        print_error(f"Dependency upgrade failed: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print_error(f"Tool not found: {e}")
        sys.exit(1)


def dev() -> None:
    """Run the development environment."""
    target = parse_target_args()

    print_task("Starting development environment...")

    procs = []

    if target in ("both", "backend"):
        print_info("Starting backend server...")
        procs.append(subprocess.Popen(["python3", "main.py"], cwd=ROOT_DIR))

    if target in ("both", "frontend"):
        print_info("Starting frontend development server...")
        procs.append(subprocess.Popen(["pnpm", "dev"], cwd=ROOT_DIR / "frontend"))

    if not procs:
        print_error(f"No servers to start for target: {target}")
        return

    server_names = {
        "both": "Development servers",
        "backend": "Backend server",
        "frontend": "Frontend server",
    }

    print_success(f"{server_names[target]} started!")
    print_info("Press Ctrl+C to stop all servers")

    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.1)
    except KeyboardInterrupt:
        print_info("Shutting down development servers...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()

        time.sleep(1)

        for p in procs:
            if p.poll() is None:
                p.kill()

        print_success("Development servers stopped!")


def format() -> None:
    """Format the codebase."""
    target = parse_target_args()

    print_task(f"Formatting {target}...")

    try:
        if target in ("both", "backend"):
            print_info("Running ruff formatter on Python code...")
            subprocess.run(["ruff", "check", ".", "--fix"], cwd=ROOT_DIR, check=True)
            print_success("Python code formatted successfully!")

        if target in ("both", "frontend"):
            print_info("Running pnpm format on frontend code...")
            subprocess.run(["pnpm", "format"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend code formatted successfully!")

        print_success(f"{target.capitalize()} formatting completed!")
    except subprocess.CalledProcessError:
        print_error("Code formatting failed!")
        raise
    except FileNotFoundError as e:
        print_error(f"Tool not found: {e}")
        raise


def lint() -> None:
    """Lint the codebase."""
    target = parse_target_args()

    print_task(f"Linting {target}...")

    try:
        if target in ("both", "backend"):
            print_info("Running ruff linter on Python code...")
            subprocess.run(["ruff", "check", "."], cwd=ROOT_DIR, check=True)
            print_success("Python code linting passed!")

        if target in ("both", "frontend"):
            print_info("Running pnpm lint on frontend code...")
            subprocess.run(["pnpm", "lint"], cwd=ROOT_DIR / "frontend", check=True)
            print_success("Frontend code linting passed!")

        print_success(f"{target.capitalize()} linting checks completed successfully!")
    except subprocess.CalledProcessError:
        print_error("Linting failed! Please fix the issues above.")
        sys.exit(1)
    except FileNotFoundError as e:
        print_error(f"Tool not found: {e}")
        sys.exit(1)


def start() -> None:
    """Start the PlexAniBridge application."""
    target = parse_target_args()

    if target == "frontend":
        print_error("Frontend cannot be started independently in production mode.")
        print_info(
            "Use 'build' to create a production build, or 'dev frontend' for "
            "development."
        )
        sys.exit(1)

    print_task("Starting PlexAniBridge application...")

    try:
        subprocess.run(["python3", "main.py"], cwd=ROOT_DIR, check=True)
        print_success("Application started successfully!")
    except subprocess.CalledProcessError as e:
        print_error(f"Application failed to start: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print_error(
            "Python3 not found! Please ensure Python 3 is installed and in your PATH."
        )
        sys.exit(1)
