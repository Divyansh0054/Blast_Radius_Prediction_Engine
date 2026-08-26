from dataclasses import dataclass

from core.risk_scorer import RiskScorer


@dataclass
class FakeCoverage:
    coverage_percent: float


class FakeCallGraph:
    def __init__(
        self,
        dependencies=None,
        dependents=None,
    ):
        self.dependencies = dependencies or set()
        self.dependents = dependents or set()

    def transitive_dependencies(self, function_name):
        return self.dependencies

    def transitive_dependents(self, function_name):
        return self.dependents


def test_structural_score():
    scorer = RiskScorer()

    graph = FakeCallGraph(
        dependencies={"a", "b"},
        dependents={"c"},
    )

    score = scorer.calculate_structural_score(
        graph,
        "foo",
    )

    assert score == 30.0


def test_structural_score_is_capped():
    scorer = RiskScorer()

    graph = FakeCallGraph(
        dependencies={
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
            "k",
        }
    )

    score = scorer.calculate_structural_score(
        graph,
        "foo",
    )

    assert score == 100.0


def test_historical_score():
    scorer = RiskScorer()

    co_changes = (
        type(
            "CoChange",
            (),
            {"frequency": 5},
        )(),
    )

    score = scorer.calculate_historical_score(
        co_changes
    )

    assert score == 50.0


def test_no_historical_changes():
    scorer = RiskScorer()

    score = scorer.calculate_historical_score(
        ()
    )

    assert score == 0.0


def test_full_coverage_has_zero_coverage_risk():
    scorer = RiskScorer()

    coverage = FakeCoverage(
        coverage_percent=100.0
    )

    score = scorer.calculate_coverage_score(
        coverage
    )

    assert score == 0.0


def test_zero_coverage_has_maximum_risk():
    scorer = RiskScorer()

    coverage = FakeCoverage(
        coverage_percent=0.0
    )

    score = scorer.calculate_coverage_score(
        coverage
    )

    assert score == 100.0


def test_missing_coverage_is_high_risk():
    scorer = RiskScorer()

    score = scorer.calculate_coverage_score(
        None
    )

    assert score == 100.0


def test_final_risk_score():
    scorer = RiskScorer()

    graph = FakeCallGraph(
        dependencies={"a", "b"},
        dependents={"c"},
    )

    co_changes = (
        type(
            "CoChange",
            (),
            {"frequency": 5},
        )(),
    )

    coverage = FakeCoverage(
        coverage_percent=50.0
    )

    result = scorer.calculate(
        call_graph=graph,
        function_name="foo",
        co_changes=co_changes,
        coverage=coverage,
    )

    assert result.structural_score == 30.0
    assert result.historical_score == 50.0
    assert result.coverage_score == 50.0

    expected = (
        30.0 * 0.40
        + 50.0 * 0.30
        + 50.0 * 0.30
    )

    assert result.final_score == expected
    assert result.risk_level == "MEDIUM"


def test_weights_must_sum_to_one():
    try:
        RiskScorer(
            structural_weight=0.5,
            historical_weight=0.5,
            coverage_weight=0.5,
        )
        assert False
    except ValueError:
        assert True


def test_real_project_integration():
    from core.ast_parser import PythonASTParser
    from core.call_graph import CallGraphBuilder
    from core.coverage_analyzer import CoverageAnalyzer
    from core.git_miner import GitHistoryMiner

    # ---------------------------------------------------------
    # 1. Real AST analysis
    # ---------------------------------------------------------

    parser = PythonASTParser()

    analysis = parser.analyze_project(
        "sample_project"
    )

    assert analysis.functions

    # ---------------------------------------------------------
    # 2. Real call graph
    # ---------------------------------------------------------

    call_graph = CallGraphBuilder(
        analysis
    ).build()

    function = analysis.functions[0]

    scorer = RiskScorer()

    structural_score = (
        scorer.calculate_structural_score(
            call_graph,
            function.qualified_name,
        )
    )

    assert 0.0 <= structural_score <= 100.0

    # ---------------------------------------------------------
    # 3. Real Git history
    # ---------------------------------------------------------

    miner = GitHistoryMiner(".")

    co_changes = miner.cochange_for_file(
        function.file_path
    )

    historical_score = (
        scorer.calculate_historical_score(
            co_changes
        )
    )

    assert 0.0 <= historical_score <= 100.0

    # ---------------------------------------------------------
    # 4. Real coverage data
    # ---------------------------------------------------------

    coverage_analyzer = CoverageAnalyzer(
        "coverage.json"
    )

    coverage_data = coverage_analyzer.data

    coverage_files = coverage_data["files"]

    assert coverage_files

    # Find an actual file from coverage.json.
    coverage_file = next(
        iter(coverage_files)
    )

    coverage_functions = coverage_files[
        coverage_file
    ]["functions"]

    assert coverage_functions

    # Find an actual function from coverage.json.
    coverage_function = next(
        iter(coverage_functions)
    )

    coverage = (
        coverage_analyzer.analyze_function(
            coverage_function,
            coverage_file,
        )
    )

    coverage_score = (
        scorer.calculate_coverage_score(
            coverage
        )
    )

    assert 0.0 <= coverage_score <= 100.0

    # ---------------------------------------------------------
    # 5. Combine all three signals
    # ---------------------------------------------------------

    result = scorer.calculate(
        call_graph=call_graph,
        function_name=function.qualified_name,
        co_changes=co_changes,
        coverage=coverage,
    )

    # Structural signal
    assert 0.0 <= result.structural_score <= 100.0

    # Historical signal
    assert 0.0 <= result.historical_score <= 100.0

    # Coverage signal
    assert 0.0 <= result.coverage_score <= 100.0

    # Final score
    assert 0.0 <= result.final_score <= 100.0

    # Risk classification
    assert result.risk_level in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }