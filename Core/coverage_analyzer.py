import json

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageInfo:
    qualified_name: str
    file_path: str
    covered_lines: int
    total_lines: int
    coverage_percent: float
    missing_lines: tuple[int, ...]


class CoverageAnalyzer:
    def __init__(self, coverage_path: str):
        self.coverage_path = coverage_path

        with open(coverage_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def analyze_function(self, qualified_name: str, file_path: str) -> CoverageInfo:
        file_data = self.data["files"][file_path]
        function_data = file_data["functions"][qualified_name]
        summary = function_data["summary"]

        return CoverageInfo(
            qualified_name=qualified_name,
            file_path=file_path,
            covered_lines=summary["covered_lines"],
            total_lines=summary["num_statements"],
            coverage_percent=summary["percent_covered"],
            missing_lines=tuple(function_data["missing_lines"]),
        )