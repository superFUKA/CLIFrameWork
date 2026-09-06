"""Build and exercise installed distributions, without importing the checkout."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"{args!r}\n{result.stdout}\n{result.stderr}")
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.stdout


def dependency_wheels(destination: Path) -> None:
    """Repack only installed pure-Python dependencies for offline verification."""
    from wheel.wheelfile import WheelFile

    for name in (["click", "colorama"] if os.name == "nt" else ["click"]):
        dist = importlib.metadata.distribution(name)
        wheel_path = destination / f"{name}-{dist.version}-py3-none-any.whl"
        with WheelFile(str(wheel_path), "w") as archive:
            for entry in dist.files or ():
                if entry.parts[0] != name and not entry.parts[0].endswith(".dist-info"):
                    continue
                if entry.name == "RECORD" or entry.suffix == ".pyc":
                    continue
                archive.write(dist.locate_file(entry), entry.as_posix())
        print(f"Offline dependency: {name} {dist.version}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    work_root = ROOT / ".review-work"
    work_root.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="distribution-", dir=work_root))
    print(f"Artifacts: {work}", flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    temp = work / "tmp"
    temp.mkdir()
    env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    source = work / "source"
    source.mkdir()
    # Build a copy to avoid touching existing egg-info/build directories.
    for name in ("src", "tests", "examples", "docs", "scripts"):
        shutil.copytree(ROOT / name, source / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "build", "dist"))
    for name in ("pyproject.toml", "README.md", "MANIFEST.in", "AGENTS.md",
                 "ARCHITECTURE.md"):
        shutil.copy2(ROOT / name, source / name)
    wheels = work / "wheels"
    wheels.mkdir()
    build = [sys.executable, "-m", "build", "--no-isolation"]
    print(run([*build, "--outdir", str(wheels), str(source)], work, env))
    print(run([*build, "--wheel", "--outdir", str(wheels),
               str(source / "examples" / "example_app")], work, env))
    if args.offline:
        dependency_wheels(wheels)
    target = work / "venv"
    venv.EnvBuilder(with_pip=True).create(target)
    binaries = target / ("Scripts" if os.name == "nt" else "bin")
    python = binaries / ("python.exe" if os.name == "nt" else "python")
    artifacts = sorted(wheels.glob("cli_framework*.whl"))
    assert len(artifacts) == 2, artifacts
    install = [str(python), "-m", "pip", "install", "--disable-pip-version-check",
               "--no-cache-dir", "--find-links", str(wheels)]
    if args.offline:
        install.append("--no-index")
    print(run([*install, *(str(path) for path in artifacts)], work, env))
    run([str(python), "-m", "pip", "check"], work, env)
    imported = run([str(python), "-c", "import cli_framework; print(cli_framework.__file__)"], work, env)
    assert Path(imported.strip()).resolve().is_relative_to(target.resolve()), imported
    entry = binaries / ("example-cli.exe" if os.name == "nt" else "example-cli")
    for prefix in ([str(entry)], [str(python), "-m", "example_cli"]):
        output = run([*prefix, "demo", "release", "build", "src", "--jobs", "2", "--clean"], work, env)
        assert output == "example:demo:active:src:jobs=2:clean=True\n", output
        output = run([*prefix, "demo", "--target", "summary"], work, env)
        assert output == "example:demo:summary\n", output
        help_text = run([*prefix, "demo", "--help"], work, env)
        assert "--target" in help_text and "release" in help_text, help_text
        result = subprocess.run([*prefix, "missing"], cwd=work, env=env,
                                capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 2 and result.stdout == "" and "No such command" in result.stderr
    print("Distribution checks passed (console entry point and python -m).")


if __name__ == "__main__":
    main()
