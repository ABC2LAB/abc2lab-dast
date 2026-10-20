"""담당 모듈의 설치와 검증을 같은 잠금 환경에서 실행한다."""

import argparse
import logging
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Module:
    """워크스페이스 모듈의 설치 이름과 검사 경로."""

    package: str
    path: str


def load_modules() -> dict[str, Module]:
    """워크스페이스 선언에서 선택 가능한 모듈을 읽는다."""
    workspace = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    modules = {}
    for pattern in workspace["tool"]["uv"]["workspace"]["members"]:
        for path in sorted(ROOT.glob(pattern)):
            metadata_path = path / "pyproject.toml"
            if not metadata_path.is_file():
                continue
            metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
            modules[path.name] = Module(
                metadata["project"]["name"], path.relative_to(ROOT).as_posix()
            )
    return modules


def run(command: list[str]) -> None:
    """실패한 단계에서 멈추고 이후 명령을 실행하지 않는다."""
    logger.info("Running: %s", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def selection(module: Module | None) -> list[str]:
    """해당 모듈의 선택 의존성도 팀원이 따로 고르지 않도록 설치한다."""
    package = ["--package", module.package] if module else ["--all-packages"]
    return ["--locked", *package, "--group", "dev", "--all-extras"]


def setup(module: Module | None) -> None:
    """의존성·커밋 훅을 설치하고 외부 서비스 없는 기본 테스트를 실행한다."""
    run(["uv", "sync", *selection(module)])
    run(["uv", "run", "--locked", "--no-sync", "pre-commit", "install", "--install-hooks"])
    tests = [f"{module.path}/tests"] if module else []
    run(["uv", "run", "--locked", "--no-sync", "pytest", *tests])
    logger.info("Setup complete: %s", module.path if module else "all modules")


def check(module: Module | None) -> None:
    """모듈은 격리 검사하고 전체 검사는 CI와 동일하게 실행한다."""
    if module:
        prefix = ["uv", "run", "--isolated", *selection(module)]
        commands = [
            ["ruff", "check", module.path],
            ["ruff", "format", "--check", module.path],
            ["mypy", f"{module.path}/src", f"{module.path}/tests"],
            ["pytest", f"{module.path}/tests"],
        ]
        for command in commands:
            run([*prefix, *command])
        return

    run(["uv", "sync", *selection(None)])
    prefix = ["uv", "run", "--locked", "--no-sync"]
    commands = [
        ["pre-commit", "run", "--all-files", "--show-diff-on-failure"],
        ["mypy"],
        ["lint-imports"],
        ["pytest"],
    ]
    for command in commands:
        run([*prefix, *command])
    run(["uv", "build", "--all-packages"])
    run([*prefix, "python", "-c", "import mcp, psycopg, psycopg_pool"])


def main() -> int:
    """모듈 이름만 받아 설치 또는 검증을 수행한다."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    modules = load_modules()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "check"])
    parser.add_argument("module", choices=[*sorted(modules), "all"])
    args = parser.parse_args()
    module = modules.get(args.module)
    try:
        if args.command == "setup":
            setup(module)
        else:
            check(module)
    except subprocess.CalledProcessError as error:
        logger.error("Step failed (exit %s). Fix the reported error and rerun.", error.returncode)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
