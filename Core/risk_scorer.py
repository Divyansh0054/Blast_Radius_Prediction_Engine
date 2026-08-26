from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.call_graph import CallGraphResult
from core.git_miner import CoChange
from core.coverage_analyzer import CoverageInfo


@dataclass(frozen=True)
class RiskResult:
    """Explainable risk score for a changed function/file."""

    structural_score: float
    historical_score: float
    coverage_score: float

    final_score: float
    risk_level: str

    structural_weight: float = 0.40
    historical_weight: float = 0.30
    coverage_weight: float = 0.30


class RiskScorer:
    """
    Combines structural, historical, and test-coverage signals
    into an explainable 0-100 risk score.
    """

    def __init__(
        self,
        structural_weight: float = 0.40,
        historical_weight: float = 0.30,
        coverage_weight: float = 0.30,
        structural_threshold: int = 10,
        historical_threshold: int = 10,
    ):
        total_weight = (
            structural_weight
            + historical_weight
            + coverage_weight
        )

        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(
                "Risk weights must sum to 1.0"
            )

        if structural_threshold <= 0:
            raise ValueError(
                "structural_threshold must be greater than 0"
            )

        if historical_threshold <= 0:
            raise ValueError(
                "historical_threshold must be greater than 0"
            )

        self.structural_weight = structural_weight
        self.historical_weight = historical_weight
        self.coverage_weight = coverage_weight

        self.structural_threshold = structural_threshold
        self.historical_threshold = historical_threshold

    def calculate_structural_score(
        self,
        call_graph: CallGraphResult,
        function_name: str,
    ) -> float:
        """
        Calculate structural risk based on the number of
        transitive dependencies and dependents.
        """

        dependencies = call_graph.transitive_dependencies(
            function_name
        )

        dependents = call_graph.transitive_dependents(
            function_name
        )

        connected_nodes = len(
            set(dependencies) | set(dependents)
        )

        return self._normalize(
            connected_nodes,
            self.structural_threshold,
        )

    def calculate_historical_score(
        self,
        co_changes: tuple[CoChange, ...],
    ) -> float:
        """
        Calculate historical risk using the strongest
        observed co-change relationship.
        """

        if not co_changes:
            return 0.0

        maximum_frequency = max(
            change.frequency
            for change in co_changes
        )

        return self._normalize(
            maximum_frequency,
            self.historical_threshold,
        )

    def calculate_coverage_score(
        self,
        coverage: Optional[CoverageInfo],
    ) -> float:
        """
        Convert test coverage into risk.

        Higher coverage means lower risk.
        """

        if coverage is None:
            return 100.0

        coverage_percent = max(
            0.0,
            min(100.0, coverage.coverage_percent),
        )

        return 100.0 - coverage_percent

    def calculate(
        self,
        call_graph: CallGraphResult,
        function_name: str,
        co_changes: tuple[CoChange, ...],
        coverage: Optional[CoverageInfo],
    ) -> RiskResult:
        """
        Combine all three signals into the final risk score.
        """

        structural_score = (
            self.calculate_structural_score(
                call_graph,
                function_name,
            )
        )

        historical_score = (
            self.calculate_historical_score(
                co_changes
            )
        )

        coverage_score = (
            self.calculate_coverage_score(
                coverage
            )
        )

        final_score = (
            structural_score * self.structural_weight
            + historical_score * self.historical_weight
            + coverage_score * self.coverage_weight
        )

        final_score = max(
            0.0,
            min(100.0, final_score),
        )

        return RiskResult(
            structural_score=structural_score,
            historical_score=historical_score,
            coverage_score=coverage_score,
            final_score=final_score,
            risk_level=self._risk_level(final_score),
            structural_weight=self.structural_weight,
            historical_weight=self.historical_weight,
            coverage_weight=self.coverage_weight,
        )

    @staticmethod
    def _normalize(
        value: int | float,
        threshold: int | float,
    ) -> float:
        """
        Normalize a value to a 0-100 range.
        """

        if value <= 0:
            return 0.0

        return min(
            100.0,
            (value / threshold) * 100.0,
        )

    @staticmethod
    def _risk_level(score: float) -> str:
        if score < 30:
            return "LOW"

        if score < 60:
            return "MEDIUM"

        if score < 80:
            return "HIGH"

        return "CRITICAL"