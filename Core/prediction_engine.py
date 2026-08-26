from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.ast_parser import PythonASTParser
from core.call_graph import CallGraphBuilder
from core.coverage_analyzer import CoverageAnalyzer
from core.git_miner import GitHistoryMiner
from core.risk_scorer import RiskScorer


@dataclass(frozen=True)
class PredictionResult:
    """
    Final blast-radius prediction for one function.
    """

    function_name: str
    file_path: str

    structural_score: float
    historical_score: float
    coverage_score: float

    final_score: float
    risk_level: str

    affected_functions: tuple[str, ...]


class PredictionEngine:
    """
    Orchestrates all blast-radius analysis components.

    Pipeline:

        AST analysis
            ↓
        Call graph
            ↓
        Historical Git analysis
            ↓
        Coverage analysis
            ↓
        Risk scoring
            ↓
        PredictionResult
    """

    def __init__(
        self,
        project_path: str | Path,
        coverage_path: str | Path,
        repo_path: str | Path | None = None,
    ):
        self.project_path = Path(
            project_path
        ).resolve()

        self.coverage_path = Path(
            coverage_path
        ).resolve()

        self.repo_path = (
            Path(repo_path).resolve()
            if repo_path is not None
            else self.project_path
        )

        self.parser = PythonASTParser()

        self.coverage_analyzer = CoverageAnalyzer(
            str(self.coverage_path)
        )

        self.git_miner = GitHistoryMiner(
            self.repo_path
        )

        self.scorer = RiskScorer()

    def analyze(
        self,
        function_name: str,
    ) -> PredictionResult:
        """
        Analyze one function and calculate its blast-radius risk.
        """

        # -----------------------------------------------------
        # 1. AST analysis
        # -----------------------------------------------------

        analysis = self.parser.analyze_project(
            str(self.project_path)
        )

        target_function = next(
            (
                function
                for function in analysis.functions
                if function.qualified_name
                == function_name
            ),
            None,
        )

        if target_function is None:
            raise ValueError(
                f"Function not found: {function_name}"
            )

        # -----------------------------------------------------
        # 2. Build call graph
        # -----------------------------------------------------

        call_graph = CallGraphBuilder(
            analysis
        ).build()

        # -----------------------------------------------------
        # 3. Structural blast radius
        # -----------------------------------------------------

        dependencies = call_graph.transitive_dependencies(
            function_name
        )

        dependents = call_graph.transitive_dependents(
            function_name
        )

        affected_functions = tuple(
            sorted(
                set(dependencies)
                | set(dependents)
            )
        )

        # -----------------------------------------------------
        # 4. Historical signal
        # -----------------------------------------------------

        co_changes = self.git_miner.cochange_for_file(
            target_function.file_path
        )

        # -----------------------------------------------------
        # 5. Coverage signal
        # -----------------------------------------------------

        coverage = self._find_coverage(
            function_name,
            target_function.file_path,
        )

        # -----------------------------------------------------
        # 6. Calculate final risk
        # -----------------------------------------------------

        result = self.scorer.calculate(
            call_graph=call_graph,
            function_name=function_name,
            co_changes=co_changes,
            coverage=coverage,
        )

        return PredictionResult(
            function_name=function_name,
            file_path=target_function.file_path,
            structural_score=result.structural_score,
            historical_score=result.historical_score,
            coverage_score=result.coverage_score,
            final_score=result.final_score,
            risk_level=result.risk_level,
            affected_functions=affected_functions,
        )

    def _find_coverage(
        self,
        function_name: str,
        file_path: str,
    ):
        """
        Find coverage information for a function.

        Coverage reports may use platform-specific paths,
        so this method normalizes paths before matching.

        Returns None when coverage is unavailable.
        """

        coverage_files = (
            self.coverage_analyzer.data
            .get("files", {})
        )

        normalized_target = (
            Path(file_path)
            .as_posix()
            .lower()
        )

        matching_file = None

        for coverage_file in coverage_files:
            normalized_coverage = (
                Path(coverage_file)
                .as_posix()
                .lower()
            )

            if (
                normalized_coverage
                == normalized_target
            ):
                matching_file = coverage_file
                break

        if matching_file is None:
            return None

        functions = coverage_files[
            matching_file
        ].get("functions", {})

        if function_name not in functions:
            return None

        return self.coverage_analyzer.analyze_function(
            function_name,
            matching_file,
        )