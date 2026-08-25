from core.coverage_analyzer import CoverageAnalyzer


def test_analyze_function():
    analyzer = CoverageAnalyzer("coverage.json")

    result = analyzer.analyze_function(
        "CallGraphResult.direct_dependencies",
        "core\\call_graph.py",
    )

    assert result.qualified_name == "CallGraphResult.direct_dependencies"
    assert result.file_path == "core\\call_graph.py"
    assert result.covered_lines == 2
    assert result.total_lines == 3
    assert result.coverage_percent == 66.66666666666667
    assert result.missing_lines == (60,)


def test_analyze_missing_function():
    analyzer = CoverageAnalyzer("coverage.json")

    try:
        analyzer.analyze_function(
            "does_not_exist",
            "core\\call_graph.py",
        )
        assert False
    except KeyError:
        assert True


def test_analyze_missing_file():
    analyzer = CoverageAnalyzer("coverage.json")

    try:
        analyzer.analyze_function(
            "some_function",
            "core\\does_not_exist.py",
        )
        assert False
    except KeyError:
        assert True