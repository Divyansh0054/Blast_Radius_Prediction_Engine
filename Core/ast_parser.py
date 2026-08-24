from pathlib import Path
from typing import Optional
import ast as python_ast
import io
import tokenize

import tree_sitter_python
from tree_sitter import Language, Parser

from core.models import (
    CallInfo,
    FunctionInfo,
    ImportInfo,
    ModuleInfo,
    ProjectAnalysis,
)


PYTHON_LANGUAGE = Language(tree_sitter_python.language())


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}


class PythonASTParser:
    """
    Structural analyzer for Python projects.

    Tree-sitter is used for source-level structural information.

    Python's built-in AST is used for Python-specific semantic
    information such as imports, scopes, and definition-time expressions.

    The parser preserves information. It does not attempt to decide
    whether a call refers to a project function, builtin, third-party
    library, or dynamic runtime object. That is the resolver's job.
    """

    def __init__(self) -> None:
        self.parser = Parser(PYTHON_LANGUAGE)

    # ============================================================
    # PUBLIC API
    # ============================================================

    def parse_file(
        self,
        file_path: Path,
        project_root: Path,
    ) -> ModuleInfo:
        """
        Parse one Python source file.
        """

        source_code = file_path.read_bytes()

        relative_path = file_path.relative_to(project_root)
        relative_path_string = relative_path.as_posix()

        module_name = self._module_name(relative_path)

        # --------------------------------------------------------
        # Determine Python source encoding.
        # --------------------------------------------------------

        encoding = self._detect_encoding(source_code)

        try:
            source_text = source_code.decode(encoding)
        except UnicodeDecodeError:
            # Tree-sitter still receives the raw bytes, but the
            # Python AST cannot safely parse the source.
            source_text = None

        # --------------------------------------------------------
        # Tree-sitter structural parsing.
        # --------------------------------------------------------

        tree = self.parser.parse(source_code)

        functions: list[FunctionInfo] = []
        calls: list[CallInfo] = []

        self._walk_tree(
            node=tree.root_node,
            source_code=source_code,
            module_name=module_name,
            relative_path=relative_path_string,
            functions=functions,
            calls=calls,
            scope=[],
            class_depth=0,
            definition_context=False,
        )

        # --------------------------------------------------------
        # Python AST semantic extraction.
        # --------------------------------------------------------

        imports: list[ImportInfo] = []
        import_parse_failed = False

        if source_text is not None:

            try:
                python_tree = python_ast.parse(
                    source_text,
                    filename=str(file_path),
                )

                imports = self._extract_imports(
                    python_tree,
                    relative_path_string,
                )

                # Python AST gives us more reliable semantics for
                # definition-time calls and imports. We use it to
                # remove calls that occur in decorators/default
                # expressions from the function's body scope.

                calls = self._refine_definition_time_calls(
                    python_tree=python_tree,
                    calls=calls,
                    source_text=source_text,
                )

            except SyntaxError:
                import_parse_failed = True

        else:
            import_parse_failed = True

        return ModuleInfo(
            module_name=module_name,
            file_path=relative_path_string,
            is_package_init=file_path.name == "__init__.py",
            functions=tuple(functions),
            calls=tuple(calls),
            imports=tuple(imports),
            has_syntax_errors=tree.root_node.has_error,
            import_parse_failed=import_parse_failed,
        )

    def analyze_project(
        self,
        project_root: str | Path,
    ) -> ProjectAnalysis:
        """
        Recursively analyze all Python files in a project.
        """

        root = Path(project_root).resolve()

        if not root.exists():
            raise FileNotFoundError(
                f"Project path does not exist: {root}"
            )

        if not root.is_dir():
            raise NotADirectoryError(
                f"Project path is not a directory: {root}"
            )

        python_files = sorted(
            path
            for path in root.rglob("*.py")
            if not self._is_ignored(path, root)
        )

        modules: list[ModuleInfo] = []

        for file_path in python_files:
            modules.append(
                self.parse_file(
                    file_path=file_path,
                    project_root=root,
                )
            )

        return ProjectAnalysis(
            root_path=str(root),
            modules=tuple(modules),
        )

    # ============================================================
    # TREE-SITTER STRUCTURAL WALK
    # ============================================================

    def _walk_tree(
        self,
        node,
        source_code: bytes,
        module_name: str,
        relative_path: str,
        functions: list[FunctionInfo],
        calls: list[CallInfo],
        scope: list[str],
        class_depth: int,
        definition_context: bool,
    ) -> None:
        """
        Walk the Tree-sitter tree.

        class_depth tracks whether we are directly inside a class.

        definition_context prevents calls in decorators/default
        expressions from being incorrectly attributed to the
        function body.
        """

        # --------------------------------------------------------
        # CLASS DEFINITION
        # --------------------------------------------------------

        if node.type == "class_definition":

            name_node = node.child_by_field_name("name")

            if name_node is not None:

                class_name = self._node_text(
                    name_node,
                    source_code,
                )

                new_scope = [
                    *scope,
                    class_name,
                ]

                # We explicitly enter the class body.
                for child in node.children:

                    self._walk_tree(
                        node=child,
                        source_code=source_code,
                        module_name=module_name,
                        relative_path=relative_path,
                        functions=functions,
                        calls=calls,
                        scope=new_scope,
                        class_depth=class_depth + 1,
                        definition_context=definition_context,
                    )

                return

        # --------------------------------------------------------
        # FUNCTION DEFINITION
        # --------------------------------------------------------

        if node.type == "function_definition":

            name_node = node.child_by_field_name("name")

            if name_node is not None:

                function_name = self._node_text(
                    name_node,
                    source_code,
                )

                qualified_name = self._qualified_name(
                    module_name=module_name,
                    scope=scope,
                    function_name=function_name,
                )

                parent_scope = (
                    "::".join(scope)
                    if scope
                    else None
                )

                # A function is a method only when it is defined
                # directly inside a class body.
                is_method = class_depth > 0

                is_async = any(
                    child.type == "async"
                    for child in node.children
                )

                functions.append(
                    FunctionInfo(
                        name=function_name,
                        qualified_name=qualified_name,
                        file_path=relative_path,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        parent_scope=parent_scope,
                        is_method=is_method,
                        is_async=is_async,
                    )
                )

                function_scope = [
                    *scope,
                    function_name,
                ]

                # Only the actual function body should be analyzed
                # as calls made by this function.
                body_node = node.child_by_field_name(
                    "body"
                )

                if body_node is not None:

                    self._walk_tree(
                        node=body_node,
                        source_code=source_code,
                        module_name=module_name,
                        relative_path=relative_path,
                        functions=functions,
                        calls=calls,
                        scope=function_scope,
                        class_depth=0,
                        definition_context=False,
                    )

                return

        # --------------------------------------------------------
        # CALL
        # --------------------------------------------------------

        if (
            node.type == "call"
            and not definition_context
        ):

            function_node = node.child_by_field_name(
                "function"
            )

            if function_node is not None:

                expression = self._node_text(
                    function_node,
                    source_code,
                )

                call_kind, qualifier, target_name = (
                    self._classify_call(
                        function_node,
                        source_code,
                    )
                )

                caller = (
                    self._qualified_name(
                        module_name=module_name,
                        scope=scope,
                        function_name=None,
                    )
                    if scope
                    else f"{module_name}::<module>"
                )

                calls.append(
                    CallInfo(
                        caller=caller,
                        expression=expression,
                        target_name=target_name,
                        call_kind=call_kind,
                        qualifier=qualifier,
                        file_path=relative_path,
                        line=function_node.start_point.row + 1,
                        column=function_node.start_point.column,
                    )
                )

        # --------------------------------------------------------
        # GENERAL RECURSION
        # --------------------------------------------------------

        for child in node.children:

            self._walk_tree(
                node=child,
                source_code=source_code,
                module_name=module_name,
                relative_path=relative_path,
                functions=functions,
                calls=calls,
                scope=scope,
                class_depth=class_depth,
                definition_context=definition_context,
            )

    # ============================================================
    # CALL CLASSIFICATION
    # ============================================================

    @staticmethod
    def _classify_call(
        function_node,
        source_code: bytes,
    ) -> tuple[str, Optional[str], str]:
        """
        Preserve the syntactic structure of a call.

        Examples:

            foo()
                -> ("name", None, "foo")

            module.foo()
                -> ("attribute", "module", "foo")

            self.foo()
                -> ("attribute", "self", "foo")

            obj.foo()
                -> ("attribute", "obj", "foo")
        """

        expression = source_code[
            function_node.start_byte:
            function_node.end_byte
        ].decode("utf-8")

        if function_node.type == "identifier":

            return (
                "name",
                None,
                expression,
            )

        if function_node.type == "attribute":

            attribute_node = function_node.child_by_field_name(
                "attribute"
            )

            object_node = function_node.child_by_field_name(
                "object"
            )

            target_name = (
                source_code[
                    attribute_node.start_byte:
                    attribute_node.end_byte
                ].decode("utf-8")
                if attribute_node is not None
                else expression.split(".")[-1]
            )

            qualifier = (
                source_code[
                    object_node.start_byte:
                    object_node.end_byte
                ].decode("utf-8")
                if object_node is not None
                else None
            )

            return (
                "attribute",
                qualifier,
                target_name,
            )

        # Calls involving more complex expressions are preserved
        # but marked as "expression" rather than pretending we know
        # their target.

        return (
            "expression",
            None,
            expression,
        )

    # ============================================================
    # IMPORT EXTRACTION
    # ============================================================

    def _extract_imports(
        self,
        tree,
        relative_path: str,
    ) -> list[ImportInfo]:
        """
        Extract imports while preserving lexical scope.

        ast.NodeVisitor is used instead of ast.walk() because we
        need to know which function/class scope contains an import.
        """

        imports: list[ImportInfo] = []

        visitor = _ImportVisitor(
            relative_path=relative_path,
            imports=imports,
        )

        visitor.visit(tree)

        return imports

    # ============================================================
    # DEFINITION-TIME CALL REFINEMENT
    # ============================================================

    @staticmethod
    def _refine_definition_time_calls(
        python_tree,
        calls: list[CallInfo],
        source_text: str,
    ) -> list[CallInfo]:
        """
        Remove calls from decorators/default expressions that
        Tree-sitter could otherwise associate with a function.

        The calls remain available when they occur in executable
        function bodies.
        """

        definition_time_ranges: list[
            tuple[int, int]
        ] = []

        class DefinitionVisitor(
            python_ast.NodeVisitor
        ):

            def visit_FunctionDef(self, node):

                # Decorators
                for decorator in node.decorator_list:

                    definition_time_ranges.append(
                        (
                            decorator.lineno,
                            getattr(
                                decorator,
                                "end_lineno",
                                decorator.lineno,
                            ),
                        )
                    )

                # Default arguments
                for default in [
                    *node.args.defaults,
                    *[
                        default
                        for default in node.args.kw_defaults
                        if default is not None
                    ],
                ]:

                    definition_time_ranges.append(
                        (
                            default.lineno,
                            getattr(
                                default,
                                "end_lineno",
                                default.lineno,
                            ),
                        )
                    )

                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node):

                for decorator in node.decorator_list:

                    definition_time_ranges.append(
                        (
                            decorator.lineno,
                            getattr(
                                decorator,
                                "end_lineno",
                                decorator.lineno,
                            ),
                        )
                    )

                for default in [
                    *node.args.defaults,
                    *[
                        default
                        for default in node.args.kw_defaults
                        if default is not None
                    ],
                ]:

                    definition_time_ranges.append(
                        (
                            default.lineno,
                            getattr(
                                default,
                                "end_lineno",
                                default.lineno,
                            ),
                        )
                    )

                self.generic_visit(node)

        visitor = DefinitionVisitor()
        visitor.visit(python_tree)

        filtered_calls: list[CallInfo] = []

        for call in calls:

            is_definition_time_call = any(
                start <= call.line <= end
                for start, end in definition_time_ranges
            )

            if not is_definition_time_call:
                filtered_calls.append(call)

        return filtered_calls

    # ============================================================
    # SOURCE ENCODING
    # ============================================================

    @staticmethod
    def _detect_encoding(
        source_code: bytes,
    ) -> str:
        """
        Detect Python source encoding using Python's tokenize
        implementation.

        Falls back to UTF-8.
        """

        try:

            encoding, _ = tokenize.detect_encoding(
                io.BytesIO(source_code).readline
            )

            return encoding

        except (SyntaxError, LookupError):

            return "utf-8"

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _node_text(
        node,
        source_code: bytes,
    ) -> str:

        return source_code[
            node.start_byte:
            node.end_byte
        ].decode("utf-8")

    @staticmethod
    def _qualified_name(
        module_name: str,
        scope: list[str],
        function_name: Optional[str],
    ) -> str:

        parts = [module_name]

        parts.extend(scope)

        if function_name:
            parts.append(function_name)

        return "::".join(parts)

    @staticmethod
    def _module_name(
        relative_path: Path,
    ) -> str:

        parts = list(
            relative_path.with_suffix("").parts
        )

        if parts and parts[-1] == "__init__":
            parts.pop()

        if not parts:
            return "<root>"

        return ".".join(parts)

    @staticmethod
    def _is_ignored(
        file_path: Path,
        project_root: Path,
    ) -> bool:

        relative_parts = file_path.relative_to(
            project_root
        ).parts

        return any(
            directory in IGNORED_DIRECTORIES
            for directory in relative_parts
        )


# ================================================================
# IMPORT VISITOR
# ================================================================

class _ImportVisitor(python_ast.NodeVisitor):
    """
    Extract imports while maintaining lexical scope.

    This visitor intentionally does not attempt to resolve imports.
    It only records what the source code declares.
    """

    def __init__(
        self,
        relative_path: str,
        imports: list[ImportInfo],
    ) -> None:

        self.relative_path = relative_path
        self.imports = imports
        self.scope: list[str] = []

    @property
    def current_scope(self) -> str:
        if not self.scope:
            return "<module>"

        return "::".join(self.scope)

    def visit_Import(self, node):

        for alias in node.names:

            bound_name = (
                alias.asname
                if alias.asname
                else alias.name.split(".")[0]
            )

            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    imported_name=None,
                    alias=alias.asname,
                    bound_name=bound_name,
                    relative_level=0,
                    scope=self.current_scope,
                    file_path=self.relative_path,
                    line=node.lineno,
                    column=node.col_offset,
                    is_from_import=False,
                    is_wildcard=False,
                )
            )

        self.generic_visit(node)

    def visit_ImportFrom(self, node):

        module_name = node.module or ""

        for alias in node.names:

            is_wildcard = alias.name == "*"

            bound_name = (
                alias.asname
                if alias.asname
                else alias.name
            )

            self.imports.append(
                ImportInfo(
                    module=module_name,
                    imported_name=alias.name,
                    alias=alias.asname,
                    bound_name=bound_name,
                    relative_level=node.level,
                    scope=self.current_scope,
                    file_path=self.relative_path,
                    line=node.lineno,
                    column=node.col_offset,
                    is_from_import=True,
                    is_wildcard=is_wildcard,
                )
            )

        self.generic_visit(node)

    def visit_FunctionDef(self, node):

        # Decorators/defaults can contain imports in unusual cases.
        # Visit those expressions in the current enclosing scope.

        for decorator in node.decorator_list:
            self.visit(decorator)

        for default in node.args.defaults:
            self.visit(default)

        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

        # Enter function scope.

        self.scope.append(node.name)

        for statement in node.body:
            self.visit(statement)

        self.scope.pop()

    def visit_AsyncFunctionDef(self, node):

        for decorator in node.decorator_list:
            self.visit(decorator)

        for default in node.args.defaults:
            self.visit(default)

        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

        self.scope.append(node.name)

        for statement in node.body:
            self.visit(statement)

        self.scope.pop()

    def visit_ClassDef(self, node):

        self.scope.append(node.name)

        for statement in node.body:
            self.visit(statement)

        self.scope.pop()


# ================================================================
# PUBLIC API
# ================================================================

def analyze_project(
    project_path: str | Path,
) -> ProjectAnalysis:

    parser = PythonASTParser()

    return parser.analyze_project(
        project_path
    )


# ================================================================
# MANUAL TEST
# ================================================================

if __name__ == "__main__":

    analysis = analyze_project(
        "sample_project"
    )

    print("AST ANALYSIS")
    print("=" * 60)

    print(
        f"Project: {analysis.root_path}"
    )

    print(
        f"Python files: {len(analysis.modules)}"
    )

    print(
        f"Functions: {len(analysis.functions)}"
    )

    print(
        f"Calls: {len(analysis.calls)}"
    )

    print(
        f"Imports: {len(analysis.imports)}"
    )

    for module in analysis.modules:

        print()
        print(
            f"FILE: {module.file_path}"
        )

        print(
            f"MODULE: {module.module_name}"
        )

        print("\nFunctions:")

        if module.functions:

            for function in module.functions:

                method_marker = (
                    " [method]"
                    if function.is_method
                    else ""
                )

                async_marker = (
                    " [async]"
                    if function.is_async
                    else ""
                )

                print(
                    f"  {function.qualified_name}"
                    f"{method_marker}"
                    f"{async_marker}"
                    f" [lines "
                    f"{function.line_start}-"
                    f"{function.line_end}]"
                )

        else:

            print("  None")

        print("\nCalls:")

        if module.calls:

            for call in module.calls:

                if call.qualifier:

                    target = (
                        f"{call.qualifier}."
                        f"{call.target_name}"
                    )

                else:

                    target = call.target_name

                print(
                    f"  {call.caller}"
                    f" -> {target}"
                    f" [{call.call_kind}]"
                    f" [line {call.line}, "
                    f"column {call.column}]"
                )

        else:

            print("  None")

        print("\nImports:")

        if module.imports:

            for import_info in module.imports:

                relative_prefix = (
                    "." * import_info.relative_level
                )

                if import_info.is_from_import:

                    imported_name = (
                        import_info.imported_name
                        or "*"
                    )

                    import_text = (
                        f"from "
                        f"{relative_prefix}"
                        f"{import_info.module} "
                        f"import "
                        f"{imported_name}"
                    )

                else:

                    import_text = (
                        f"import "
                        f"{import_info.module}"
                    )

                if import_info.alias:

                    import_text += (
                        f" as {import_info.alias}"
                    )

                print(
                    f"  {import_text}"
                    f" [bound={import_info.bound_name}]"
                    f" [scope={import_info.scope}]"
                    f" [line={import_info.line}]"
                )

        else:

            print("  None")

        if module.has_syntax_errors:

            print(
                "\nWARNING: "
                "Tree-sitter detected syntax errors."
            )

        if module.import_parse_failed:

            print(
                "\nWARNING: "
                "Python AST semantic parsing failed."
            )