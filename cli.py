from __future__ import annotations

from pathlib import Path

import typer

from core.prediction_engine import PredictionEngine


app = typer.Typer(
    help="Blast Radius Prediction Engine"
)


@app.command("analyze")
def analyze(
    project: Path = typer.Option(
        ...,
        "--project",
        "-p",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Path to the Python project.",
    ),
    function: str = typer.Option(
        ...,
        "--function",
        "-f",
        help="Qualified function name to analyze.",
    ),
    coverage: Path = typer.Option(
        ...,
        "--coverage",
        "-c",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to coverage.json.",
    ),
    repo: Path | None = typer.Option(
        None,
        "--repo",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Path to Git repository. Defaults to current directory.",
    ),
) -> None:
    """Analyze a function and predict its blast radius."""

    repo_path = repo if repo is not None else Path.cwd()

    try:
        engine = PredictionEngine(
            project_path=project,
            coverage_path=coverage,
            repo_path=repo_path,
        )

        result = engine.analyze(function)

    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Blast Radius Prediction")
    typer.echo("=======================")
    typer.echo(f"Function:          {result.function_name}")
    typer.echo(f"File:              {result.file_path}")
    typer.echo(f"Structural Score:  {result.structural_score:.2f}")
    typer.echo(f"Historical Score:  {result.historical_score:.2f}")
    typer.echo(f"Coverage Score:    {result.coverage_score:.2f}")
    typer.echo(f"Final Risk Score:  {result.final_score:.2f}")
    typer.echo(f"Risk Level:        {result.risk_level}")

    typer.echo("")
    typer.echo("Affected Functions")
    typer.echo("------------------")

    if result.affected_functions:
        for affected_function in result.affected_functions:
            typer.echo(f"- {affected_function}")
    else:
        typer.echo("None")


@app.command("version")
def version() -> None:
    """Show the current engine version."""

    typer.echo("Blast Radius Prediction Engine v1.0.0")


if __name__ == "__main__":
    app()