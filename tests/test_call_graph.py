from pathlib import Path

from core.ast_parser import PythonASTParser
from core.call_graph import CallGraphBuilder


def create_project(tmp_path: Path, files: dict[str, str]) -> Path:
    project = tmp_path / "project"
    project.mkdir()

    for relative_path, content in files.items():
        file_path = project / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return project


def build_graph(tmp_path: Path, files: dict[str, str]):
    project = create_project(tmp_path, files)

    analysis = PythonASTParser().analyze_project(project)

    return CallGraphBuilder(analysis).build()


# ============================================================
# BASIC RESOLUTION
# ============================================================

def test_from_import_resolves_function(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from calculator import calculate

def main():
    calculate()
""",
            "calculator.py": """
def calculate():
    pass
""",
        },
    )

    assert (
        "main::main",
        "calculator::calculate",
    ) in result.graph.edges


def test_transitive_dependency(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from calculator import calculate

def main():
    calculate()
""",
            "calculator.py": """
from utils import add

def calculate():
    add()
""",
            "utils.py": """
def add():
    pass
""",
        },
    )

    assert (
        "main::main",
        "calculator::calculate",
    ) in result.graph.edges

    assert (
        "calculator::calculate",
        "utils::add",
    ) in result.graph.edges

    dependencies = result.transitive_dependencies(
        "main::main"
    )

    assert dependencies == {
        "calculator::calculate",
        "utils::add",
    }


# ============================================================
# EXTERNAL / UNRESOLVED CALLS
# ============================================================

def test_external_function_is_unresolved(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
def main():
    print("hello")
""",
        },
    )

    assert (
        "main::main",
        "print",
    ) not in result.graph.edges

    assert any(
        call.expression == "print"
        for call in result.unresolved_calls
    )


# ============================================================
# MODULE IMPORTS
# ============================================================

def test_module_attribute_call_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
import calculator

def main():
    calculator.calculate()
""",
            "calculator.py": """
def calculate():
    pass
""",
        },
    )

    assert (
        "main::main",
        "calculator::calculate",
    ) in result.graph.edges


def test_import_alias_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
import calculator as calc

def main():
    calc.calculate()
""",
            "calculator.py": """
def calculate():
    pass
""",
        },
    )

    assert (
        "main::main",
        "calculator::calculate",
    ) in result.graph.edges


def test_from_import_alias_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from calculator import calculate as calc

def main():
    calc()
""",
            "calculator.py": """
def calculate():
    pass
""",
        },
    )

    assert (
        "main::main",
        "calculator::calculate",
    ) in result.graph.edges


# ============================================================
# CLASS / METHOD RESOLUTION
# ============================================================

def test_self_method_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "service.py": """
class Service:

    def run(self):
        self.process()

    def process(self):
        pass
""",
        },
    )

    assert (
        "service::Service::run",
        "service::Service::process",
    ) in result.graph.edges


# ============================================================
# RECURSION
# ============================================================

def test_recursive_function_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
def countdown(n):
    if n > 0:
        countdown(n - 1)
""",
        },
    )

    assert (
        "main::countdown",
        "main::countdown",
    ) in result.graph.edges


# ============================================================
# MODULE-LEVEL CALL
# ============================================================

def test_module_level_call_resolves(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
def main():
    pass

main()
""",
        },
    )

    assert (
        "main::<module>",
        "main::main",
    ) in result.graph.edges


# ============================================================
# DEPENDENCY / DEPENDENT HELPERS
# ============================================================

def test_direct_dependencies(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from utils import helper

def main():
    helper()
""",
            "utils.py": """
def helper():
    pass
""",
        },
    )

    assert result.direct_dependencies(
        "main::main"
    ) == ["utils::helper"]


def test_direct_dependents(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from utils import helper

def main():
    helper()
""",
            "utils.py": """
def helper():
    pass
""",
        },
    )

    assert result.direct_dependents(
        "utils::helper"
    ) == ["main::main"]


def test_transitive_dependents(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
from calculator import calculate

def main():
    calculate()
""",
            "calculator.py": """
from utils import add

def calculate():
    add()
""",
            "utils.py": """
def add():
    pass
""",
        },
    )

    dependents = result.transitive_dependents(
        "utils::add"
    )

    assert dependents == {
        "calculator::calculate",
        "main::main",
    }


# ============================================================
# AMBIGUOUS FUNCTIONS
# ============================================================

def test_ambiguous_function_name_is_not_guessed(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "a.py": """
def process():
    pass
""",
            "b.py": """
def process():
    pass
""",
            "main.py": """
def main():
    process()
""",
        },
    )

    assert (
        "main::main",
        "a::process",
    ) not in result.graph.edges

    assert (
        "main::main",
        "b::process",
    ) not in result.graph.edges

    assert any(
        "multiple project functions"
        in call.reason
        for call in result.unresolved_calls
    )


# ============================================================
# OBJECT METHOD SHOULD NOT BE GUESSED
# ============================================================

def test_unknown_object_method_is_unresolved(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "main.py": """
def main(obj):
    obj.process()
""",
        },
    )

    assert len(result.graph.edges) == 0

    assert any(
        call.expression == "obj.process"
        for call in result.unresolved_calls
    )


# ============================================================
# GRAPH NODE COVERAGE
# ============================================================

def test_all_project_functions_are_graph_nodes(tmp_path):
    result = build_graph(
        tmp_path,
        {
            "a.py": """
def first():
    pass

def second():
    pass
""",
        },
    )

    assert "a::first" in result.graph.nodes
    assert "a::second" in result.graph.nodes