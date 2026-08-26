from core.prediction_engine import PredictionEngine


def test_prediction_engine_can_analyze_sample_project():
    engine = PredictionEngine(
        project_path="sample_project",
        coverage_path="coverage.json",
        repo_path=".",
    )

    result = engine.analyze(
        "calculator::calculate"
    )

    assert result.function_name == (
        "calculator::calculate"
    )

    assert result.file_path == "calculator.py"

    assert 0.0 <= result.structural_score <= 100.0

    assert 0.0 <= result.historical_score <= 100.0

    assert 0.0 <= result.coverage_score <= 100.0

    assert 0.0 <= result.final_score <= 100.0

    assert result.risk_level in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }


def test_missing_coverage_is_handled():
    engine = PredictionEngine(
        project_path="sample_project",
        coverage_path="coverage.json",
        repo_path=".",
    )

    result = engine.analyze(
        "calculator::calculate"
    )

    # calculator.py is not present in the current
    # coverage.json, so the scorer should treat it
    # as maximum coverage risk.
    assert result.coverage_score == 100.0


def test_unknown_function_raises_error():
    engine = PredictionEngine(
        project_path="sample_project",
        coverage_path="coverage.json",
        repo_path=".",
    )

    try:
        engine.analyze(
            "does_not_exist::function"
        )
        assert False
    except ValueError as exc:
        assert "Function not found" in str(exc)