from typer.testing import CliRunner

from cli import app


runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Blast Radius Prediction Engine" in result.stdout
    assert "v1.0.0" in result.stdout


def test_analyze_sample_project():
    result = runner.invoke(
        app,
        [
            "analyze",
            "--project",
            "sample_project",
            "--function",
            "calculator::calculate",
            "--coverage",
            "coverage.json",
            "--repo",
            ".",
        ],
    )

    assert result.exit_code == 0
    assert "Blast Radius Prediction" in result.stdout
    assert "calculator::calculate" in result.stdout
    assert "Risk Level:" in result.stdout
    assert "Final Risk Score:" in result.stdout


def test_unknown_function_returns_error():
    result = runner.invoke(
        app,
        [
            "analyze",
            "--project",
            "sample_project",
            "--function",
            "calculator::does_not_exist",
            "--coverage",
            "coverage.json",
            "--repo",
            ".",
        ],
    )

    assert result.exit_code != 0
    assert "Error:" in result.stderr