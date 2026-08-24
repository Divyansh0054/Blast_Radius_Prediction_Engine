from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SourceLocation:
    """
    Source location within a source file.

    Lines are 1-based.
    Columns are 0-based byte offsets, matching Tree-sitter.
    """

    line: int
    column: int


@dataclass(frozen=True)
class FunctionInfo:
    """
    Represents a function or method discovered in a Python source file.

    qualified_name is the canonical identity used by later components.

    Examples:
        module::foo
        module::Class::foo
        module::outer::inner
    """

    name: str
    qualified_name: str
    file_path: str

    line_start: int
    line_end: int

    parent_scope: Optional[str] = None

    is_method: bool = False
    is_async: bool = False


@dataclass(frozen=True)
class CallInfo:
    """
    Represents a syntactic function/method call.

    The parser preserves syntax here. It does NOT decide whether
    the call refers to a project function, builtin, third-party
    library, or unresolved runtime object.

    Examples:

        foo()
            call_kind = "name"
            target_name = "foo"

        module.foo()
            call_kind = "attribute"
            qualifier = "module"
            target_name = "foo"

        self.foo()
            call_kind = "attribute"
            qualifier = "self"
            target_name = "foo"
    """

    caller: str

    expression: str

    target_name: str

    call_kind: str

    qualifier: Optional[str]

    file_path: str

    line: int
    column: int


@dataclass(frozen=True)
class ImportInfo:
    """
    Represents a Python import.

    bound_name is the name introduced into the current scope.

    Examples:

        import calculator

        module:
            calculator

        imported_name:
            None

        bound_name:
            calculator


        import calculator as calc

        module:
            calculator

        bound_name:
            calc


        from calculator import calculate

        module:
            calculator

        imported_name:
            calculate

        bound_name:
            calculate


        from calculator import calculate as calc

        module:
            calculator

        imported_name:
            calculate

        bound_name:
            calc

    relative_level:
        0 = absolute import
        1 = from .module import ...
        2 = from ..module import ...
    """

    module: str

    imported_name: Optional[str]

    alias: Optional[str]

    bound_name: str

    relative_level: int

    scope: str

    file_path: str

    line: int

    column: int

    is_from_import: bool

    is_wildcard: bool = False


@dataclass(frozen=True)
class ModuleInfo:
    """
    Structural information extracted from one Python source file.
    """

    module_name: str

    file_path: str

    is_package_init: bool = False

    functions: tuple[FunctionInfo, ...] = field(
        default_factory=tuple
    )

    calls: tuple[CallInfo, ...] = field(
        default_factory=tuple
    )

    imports: tuple[ImportInfo, ...] = field(
        default_factory=tuple
    )

    has_syntax_errors: bool = False

    import_parse_failed: bool = False


@dataclass(frozen=True)
class ProjectAnalysis:
    """
    Complete structural analysis of a Python project.
    """

    root_path: str

    modules: tuple[ModuleInfo, ...] = field(
        default_factory=tuple
    )

    @property
    def functions(self) -> tuple[FunctionInfo, ...]:
        return tuple(
            function
            for module in self.modules
            for function in module.functions
        )

    @property
    def calls(self) -> tuple[CallInfo, ...]:
        return tuple(
            call
            for module in self.modules
            for call in module.calls
        )

    @property
    def imports(self) -> tuple[ImportInfo, ...]:
        return tuple(
            import_info
            for module in self.modules
            for import_info in module.imports
        )