from pathlib import Path

from core.ast_parser import PythonASTParser


def create_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """
    Create a temporary Python project for testing.
    """

    project = tmp_path / "project"
    project.mkdir()

    for relative_path, content in files.items():

        file_path = project / relative_path

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_path.write_text(
            content,
            encoding="utf-8",
        )

    return project


def analyze(tmp_path: Path, files: dict[str, str]):
    """
    Create and analyze a temporary project.
    """

    project = create_project(
        tmp_path,
        files,
    )

    parser = PythonASTParser()

    return parser.analyze_project(project)


# ============================================================
# IMPORT TESTS
# ============================================================


def test_simple_import(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
import utils
""",
        },
    )

    imports = analysis.imports

    assert len(imports) == 1

    import_info = imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name is None
    assert import_info.alias is None
    assert import_info.bound_name == "utils"
    assert import_info.relative_level == 0
    assert import_info.scope == "<module>"
    assert import_info.is_from_import is False
    assert import_info.is_wildcard is False


def test_import_with_alias(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
import utils as u
""",
        },
    )

    import_info = analysis.imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name is None
    assert import_info.alias == "u"
    assert import_info.bound_name == "u"


def test_from_import(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
from utils import add
""",
        },
    )

    import_info = analysis.imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name == "add"
    assert import_info.alias is None
    assert import_info.bound_name == "add"
    assert import_info.relative_level == 0
    assert import_info.is_from_import is True


def test_from_import_with_alias(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
from utils import add as plus
""",
        },
    )

    import_info = analysis.imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name == "add"
    assert import_info.alias == "plus"
    assert import_info.bound_name == "plus"


def test_multiple_from_imports(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
from utils import add, subtract
""",
        },
    )

    imports = analysis.imports

    assert len(imports) == 2

    imported_names = {
        item.imported_name
        for item in imports
    }

    bound_names = {
        item.bound_name
        for item in imports
    }

    assert imported_names == {
        "add",
        "subtract",
    }

    assert bound_names == {
        "add",
        "subtract",
    }


def test_relative_import(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "package/__init__.py": "",
            "package/main.py": """
from .utils import add
""",
            "package/utils.py": "",
        },
    )

    imports = analysis.imports

    assert len(imports) == 1

    import_info = imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name == "add"
    assert import_info.bound_name == "add"
    assert import_info.relative_level == 1


def test_double_relative_import(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "package/__init__.py": "",
            "package/sub/__init__.py": "",
            "package/sub/main.py": """
from ..utils import add
""",
            "package/utils.py": "",
        },
    )

    imports = analysis.imports

    assert len(imports) == 1

    import_info = imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name == "add"
    assert import_info.relative_level == 2


def test_wildcard_import(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
from utils import *
""",
        },
    )

    import_info = analysis.imports[0]

    assert import_info.module == "utils"
    assert import_info.imported_name == "*"
    assert import_info.bound_name == "*"
    assert import_info.is_wildcard is True


def test_local_import_scope(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def foo():
    import calculator
""",
        },
    )

    imports = analysis.imports

    assert len(imports) == 1

    import_info = imports[0]

    assert import_info.module == "calculator"
    assert import_info.bound_name == "calculator"
    assert import_info.scope == "foo"


def test_nested_local_import_scope(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def outer():

    def inner():
        import calculator

""",
        },
    )

    imports = analysis.imports

    assert len(imports) == 1

    assert imports[0].scope == "outer::inner"


# ============================================================
# FUNCTION TESTS
# ============================================================


def test_top_level_function(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def foo():
    pass
""",
        },
    )

    functions = analysis.functions

    assert len(functions) == 1

    function = functions[0]

    assert function.name == "foo"
    assert function.qualified_name == "main::foo"
    assert function.is_method is False
    assert function.is_async is False


def test_class_method(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class A:

    def foo(self):
        pass
""",
        },
    )

    functions = analysis.functions

    assert len(functions) == 1

    function = functions[0]

    assert function.qualified_name == "main::A::foo"
    assert function.is_method is True
    assert function.is_async is False


def test_nested_function_is_not_method(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class A:

    def outer(self):

        def inner():
            pass

        inner()
""",
        },
    )

    functions = {
        function.qualified_name: function
        for function in analysis.functions
    }

    assert "main::A::outer" in functions
    assert "main::A::outer::inner" in functions

    assert functions[
        "main::A::outer"
    ].is_method is True

    assert functions[
        "main::A::outer::inner"
    ].is_method is False


def test_nested_class(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class Outer:

    class Inner:

        def foo(self):
            pass
""",
        },
    )

    functions = analysis.functions

    assert len(functions) == 1

    assert (
        functions[0].qualified_name
        == "main::Outer::Inner::foo"
    )

    assert functions[0].is_method is True


def test_async_function(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
async def fetch():
    pass
""",
        },
    )

    function = analysis.functions[0]

    assert function.name == "fetch"
    assert function.qualified_name == "main::fetch"
    assert function.is_async is True


def test_nested_function_inside_method(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class Service:

    def run(self):

        def helper():
            pass

        helper()
""",
        },
    )

    functions = {
        function.qualified_name: function
        for function in analysis.functions
    }

    assert functions[
        "main::Service::run"
    ].is_method is True

    assert functions[
        "main::Service::run::helper"
    ].is_method is False


def test_duplicate_function_names_in_classes(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class A:

    def process(self):
        pass


class B:

    def process(self):
        pass
""",
        },
    )

    qualified_names = {
        function.qualified_name
        for function in analysis.functions
    }

    assert "main::A::process" in qualified_names
    assert "main::B::process" in qualified_names


# ============================================================
# CALL TESTS
# ============================================================


def test_simple_function_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def foo():
    pass


def bar():
    foo()
""",
        },
    )

    calls = analysis.calls

    foo_call = next(
        call
        for call in calls
        if call.target_name == "foo"
    )

    assert foo_call.call_kind == "name"
    assert foo_call.qualifier is None
    assert foo_call.expression == "foo"
    assert foo_call.caller == "main::bar"


def test_module_attribute_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
import utils

def foo():
    utils.add()
""",
        },
    )

    call = next(
        call
        for call in analysis.calls
        if call.target_name == "add"
    )

    assert call.call_kind == "attribute"
    assert call.qualifier == "utils"
    assert call.expression == "utils.add"


def test_self_method_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
class Service:

    def run(self):
        self.process()

    def process(self):
        pass
""",
        },
    )

    call = next(
        call
        for call in analysis.calls
        if call.target_name == "process"
    )

    assert call.call_kind == "attribute"
    assert call.qualifier == "self"
    assert call.expression == "self.process"
    assert call.caller == "main::Service::run"


def test_object_method_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def run(obj):
    obj.process()
""",
        },
    )

    call = next(
        call
        for call in analysis.calls
        if call.target_name == "process"
    )

    assert call.call_kind == "attribute"
    assert call.qualifier == "obj"
    assert call.expression == "obj.process"


def test_nested_calls(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def foo():
    pass


def bar():
    foo(print())
""",
        },
    )

    target_names = [
        call.target_name
        for call in analysis.calls
    ]

    assert "foo" in target_names
    assert "print" in target_names


def test_recursive_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def countdown(n):

    if n > 0:
        countdown(n - 1)
""",
        },
    )

    call = next(
        call
        for call in analysis.calls
        if call.target_name == "countdown"
    )

    assert call.caller == "main::countdown"
    assert call.call_kind == "name"


def test_module_level_call(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def foo():
    pass

foo()
""",
        },
    )

    call = next(
        call
        for call in analysis.calls
        if call.target_name == "foo"
    )

    assert call.caller == "main::<module>"


# ============================================================
# DEFINITION-TIME CALL TESTS
# ============================================================


def test_decorator_call_not_attributed_to_function(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def register():
    pass


@register()
def foo():
    pass
""",
        },
    )

    foo_calls = [
        call
        for call in analysis.calls
        if call.caller == "main::foo"
    ]

    assert foo_calls == []


def test_default_argument_call_not_attributed_to_function(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def make_default():
    return 1


def foo(value=make_default()):
    pass
""",
        },
    )

    foo_calls = [
        call
        for call in analysis.calls
        if call.caller == "main::foo"
    ]

    assert foo_calls == []


# ============================================================
# ROBUSTNESS TESTS
# ============================================================


def test_unicode_source(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
message = "नमस्ते"


def greet():
    print(message)
""",
        },
    )

    assert len(analysis.functions) == 1

    assert (
        analysis.functions[0].qualified_name
        == "main::greet"
    )


def test_syntax_error_does_not_crash_project_analysis(
    tmp_path,
):
    analysis = analyze(
        tmp_path,
        {
            "broken.py": """
def broken(
""",
            "working.py": """
def working():
    pass
""",
        },
    )

    broken_module = next(
        module
        for module in analysis.modules
        if module.file_path == "broken.py"
    )

    working_module = next(
        module
        for module in analysis.modules
        if module.file_path == "working.py"
    )

    assert broken_module.has_syntax_errors is True

    assert (
        working_module.has_syntax_errors
        is False
    )


def test_init_file_is_analyzed(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "package/__init__.py": """
def initialize():
    pass
""",
        },
    )

    assert len(analysis.modules) == 1

    module = analysis.modules[0]

    assert module.file_path == "package/__init__.py"

    assert module.module_name == "package"

    assert (
        module.functions[0].qualified_name
        == "package::initialize"
    )


def test_nested_package_structure(tmp_path):
    analysis = analyze(
        tmp_path,
        {
            "package/__init__.py": "",
            "package/sub/__init__.py": "",
            "package/sub/service.py": """
def process():
    pass
""",
        },
    )

    service = next(
        module
        for module in analysis.modules
        if module.file_path
        == "package/sub/service.py"
    )

    assert service.module_name == (
        "package.sub.service"
    )


def test_ignored_directories_are_not_analyzed(
    tmp_path,
):
    analysis = analyze(
        tmp_path,
        {
            "main.py": """
def main():
    pass
""",
            ".venv/fake.py": """
def fake():
    pass
""",
            "__pycache__/fake.py": """
def fake():
    pass
""",
            "node_modules/fake.py": """
def fake():
    pass
""",
        },
    )

    file_paths = {
        module.file_path
        for module in analysis.modules
    }

    assert "main.py" in file_paths

    assert ".venv/fake.py" not in file_paths
    assert "__pycache__/fake.py" not in file_paths
    assert "node_modules/fake.py" not in file_paths