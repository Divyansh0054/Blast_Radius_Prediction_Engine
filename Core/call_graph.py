from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import networkx as nx

from core.models import (
    CallInfo,
    FunctionInfo,
    ImportInfo,
    ProjectAnalysis,
)


@dataclass(frozen=True)
class ResolvedCall:
    """A call that has been resolved to a project function."""

    caller: str
    callee: str
    file_path: str
    line: int


@dataclass(frozen=True)
class UnresolvedCall:
    """A call that could not be resolved to a project function."""

    caller: str
    expression: str
    file_path: str
    line: int
    reason: str


@dataclass
class CallGraphResult:
    """Complete result of call resolution and graph construction."""

    graph: nx.DiGraph

    resolved_calls: list[ResolvedCall] = field(
        default_factory=list
    )

    unresolved_calls: list[UnresolvedCall] = field(
        default_factory=list
    )

    # ============================================================
    # GRAPH HELPERS
    # ============================================================

    def direct_dependencies(
        self,
        function_name: str,
    ) -> list[str]:

        if function_name not in self.graph:
            return []

        return list(
            self.graph.successors(function_name)
        )

    def direct_dependents(
        self,
        function_name: str,
    ) -> list[str]:

        if function_name not in self.graph:
            return []

        return list(
            self.graph.predecessors(function_name)
        )

    def transitive_dependencies(
        self,
        function_name: str,
    ) -> set[str]:

        if function_name not in self.graph:
            return set()

        return nx.descendants(
            self.graph,
            function_name,
        )

    def transitive_dependents(
        self,
        function_name: str,
    ) -> set[str]:

        if function_name not in self.graph:
            return set()

        return nx.ancestors(
            self.graph,
            function_name,
        )


class CallGraphBuilder:
    """
    Resolves syntactic calls from the AST parser to functions
    defined inside the analyzed project.

    The resolver deliberately does NOT attempt full Python type
    inference. Dynamic calls that cannot be justified are kept
    as unresolved instead of being guessed.
    """

    def __init__(
        self,
        analysis: ProjectAnalysis,
    ) -> None:

        self.analysis = analysis

        # --------------------------------------------------------
        # Function indexes
        # --------------------------------------------------------

        self.functions_by_qualified_name: dict[
            str,
            FunctionInfo,
        ] = {
            function.qualified_name: function
            for function in analysis.functions
        }

        self.functions_by_name: dict[
            str,
            list[FunctionInfo],
        ] = {}

        for function in analysis.functions:

            self.functions_by_name.setdefault(
                function.name,
                [],
            ).append(function)

        # --------------------------------------------------------
        # Module indexes
        # --------------------------------------------------------

        self.modules_by_name = {
            module.module_name: module
            for module in analysis.modules
        }

        # --------------------------------------------------------
        # Import lookup
        #
        # Key:
        #     (file_path, scope, bound_name)
        #
        # Example:
        #
        #     ("main.py", "<module>", "calculate")
        #
        #     -> calculator::calculate
        # --------------------------------------------------------

        self.imports_by_scope: dict[
            tuple[str, str, str],
            ImportInfo,
        ] = {}

        for import_info in analysis.imports:

            key = (
                import_info.file_path,
                import_info.scope,
                import_info.bound_name,
            )

            self.imports_by_scope[key] = import_info

    # ============================================================
    # PUBLIC API
    # ============================================================

    def build(self) -> CallGraphResult:
        """
        Resolve all calls and construct a directed graph.

        Edge direction:

            caller -> callee

        Therefore:

            main::main
                ↓
            calculator::calculate
                ↓
            utils::add
        """

        graph = nx.DiGraph()

        # --------------------------------------------------------
        # Add every project function as a node.
        # --------------------------------------------------------

        for function in self.analysis.functions:

            graph.add_node(
                function.qualified_name,
                node_type="function",
                file_path=function.file_path,
                function_name=function.name,
            )

        resolved_calls: list[ResolvedCall] = []
        unresolved_calls: list[UnresolvedCall] = []

        # --------------------------------------------------------
        # Resolve calls.
        # --------------------------------------------------------

        for call in self.analysis.calls:

            resolved_target, reason = self._resolve_call(
                call
            )

            if resolved_target is None:

                unresolved_calls.append(
                    UnresolvedCall(
                        caller=call.caller,
                        expression=call.expression,
                        file_path=call.file_path,
                        line=call.line,
                        reason=reason,
                    )
                )

                continue

            # ----------------------------------------------------
            # Don't add self-loop unless the function is actually
            # recursive.
            # ----------------------------------------------------

            graph.add_edge(
                call.caller,
                resolved_target,
                line=call.line,
            )

            resolved_calls.append(
                ResolvedCall(
                    caller=call.caller,
                    callee=resolved_target,
                    file_path=call.file_path,
                    line=call.line,
                )
            )

        return CallGraphResult(
            graph=graph,
            resolved_calls=resolved_calls,
            unresolved_calls=unresolved_calls,
        )

    # ============================================================
    # CALL RESOLUTION
    # ============================================================

    def _resolve_call(
        self,
        call: CallInfo,
    ) -> tuple[Optional[str], str]:
        """
        Resolve one call.

        Returns:

            (qualified_function_name, reason)

        or:

            (None, reason)
        """

        # --------------------------------------------------------
        # Simple name:
        #
        #     calculate()
        #     add()
        # --------------------------------------------------------

        if call.call_kind == "name":

            return self._resolve_name_call(
                call
            )

        # --------------------------------------------------------
        # Attribute:
        #
        #     calculator.calculate()
        #     self.process()
        #     obj.process()
        # --------------------------------------------------------

        if call.call_kind == "attribute":

            return self._resolve_attribute_call(
                call
            )

        return (
            None,
            "complex expression cannot be statically resolved",
        )

    # ============================================================
    # SIMPLE NAME RESOLUTION
    # ============================================================

    def _resolve_name_call(
        self,
        call: CallInfo,
    ) -> tuple[Optional[str], str]:

        # --------------------------------------------------------
        # Determine the caller's lexical scope.
        #
        # Example:
        #
        #     main::main
        #
        # scope:
        #
        #     main
        #     main::main
        # --------------------------------------------------------

        caller_scope = self._caller_scope_chain(
            call.caller
        )

        # --------------------------------------------------------
        # 1. Check local imports from nearest scope outward.
        # --------------------------------------------------------

        for scope in reversed(caller_scope):

            import_info = self.imports_by_scope.get(
                (
                    call.file_path,
                    scope,
                    call.target_name,
                )
            )

            if import_info is not None:

                resolved = self._resolve_import(
                    import_info
                )

                if resolved is not None:

                    return (
                        resolved,
                        "resolved through import",
                    )

        # --------------------------------------------------------
        # 2. Look for a function in the same module.
        #
        # Example:
        #
        #     main::foo -> main::bar
        # --------------------------------------------------------

        module_name = self._module_name_from_call(
            call.caller
        )

        same_module_candidates = [
            function
            for function in self.functions_by_name.get(
                call.target_name,
                [],
            )
            if function.qualified_name.startswith(
                module_name + "::"
            )
        ]

        if len(same_module_candidates) == 1:

            return (
                same_module_candidates[0].qualified_name,
                "resolved to unique same-module function",
            )

        # --------------------------------------------------------
        # 3. Resolve a method/function in the caller's class.
        # --------------------------------------------------------

        caller_function = (
            self.functions_by_qualified_name.get(
                call.caller
            )
        )

        if caller_function is not None:

            parent_scope = caller_function.parent_scope

            if parent_scope:

                candidate = (
                    f"{parent_scope}::"
                    f"{call.target_name}"
                )

                if candidate in (
                    self.functions_by_qualified_name
                ):

                    return (
                        candidate,
                        "resolved to same-class function",
                    )

        # --------------------------------------------------------
        # 4. Unique project-wide function name.
        #
        # This is intentionally conservative:
        # only resolve when there is exactly one candidate.
        # --------------------------------------------------------

        candidates = self.functions_by_name.get(
            call.target_name,
            [],
        )

        if len(candidates) == 1:

            return (
                candidates[0].qualified_name,
                "resolved to unique project function",
            )

        if len(candidates) > 1:

            return (
                None,
                "multiple project functions have this name",
            )

        # --------------------------------------------------------
        # 5. No project function.
        #
        # Could be:
        #     print()
        #     len()
        #     library_function()
        # --------------------------------------------------------

        return (
            None,
            "no matching project function",
        )

    # ============================================================
    # ATTRIBUTE RESOLUTION
    # ============================================================

    def _resolve_attribute_call(
        self,
        call: CallInfo,
    ) -> tuple[Optional[str], str]:

        qualifier = call.qualifier

        if qualifier is None:

            return (
                None,
                "attribute call has no qualifier",
            )

        # --------------------------------------------------------
        # module.function()
        #
        # Example:
        #
        #     calculator.calculate()
        # --------------------------------------------------------

        module = self._resolve_module_alias(
            call.file_path,
            call.caller,
            qualifier,
        )

        if module is not None:

            candidate = (
                f"{module}::{call.target_name}"
            )

            if candidate in (
                self.functions_by_qualified_name
            ):

                return (
                    candidate,
                    "resolved module attribute call",
                )

        # --------------------------------------------------------
        # self.method()
        #
        # Resolve against the caller's class.
        # --------------------------------------------------------

        if qualifier == "self":

            caller_function = (
                self.functions_by_qualified_name.get(
                    call.caller
                )
            )

            if caller_function is not None:

                caller_parts = call.caller.split("::")

                # The last component is the current function.
                # The components before it represent the enclosing scope.
                scope_parts = caller_parts[:-1]

                if len(scope_parts) >= 2:

                    class_scope = "::".join(
                        scope_parts
                    )

                    candidate = (
                        f"{class_scope}::"
                        f"{call.target_name}"
                    )

                    if candidate in (
                        self.functions_by_qualified_name
                    ):

                        return (
                            candidate,
                            "resolved self method call",
                        )

        # --------------------------------------------------------
        # ClassName.method()
        #
        # --------------------------------------------------------

        class_candidates = [
            function
            for function in self.functions_by_name.get(
                call.target_name,
                [],
            )
            if self._qualifier_matches_class(
                qualifier,
                function,
            )
        ]

        if len(class_candidates) == 1:

            return (
                class_candidates[0].qualified_name,
                "resolved class attribute call",
            )

        # --------------------------------------------------------
        # obj.method()
        #
        # We cannot safely determine obj's runtime type without
        # type inference. Don't guess.
        # --------------------------------------------------------

        return (
            None,
            "object attribute cannot be statically resolved",
        )

    # ============================================================
    # IMPORT RESOLUTION
    # ============================================================

    def _resolve_import(
        self,
        import_info: ImportInfo,
    ) -> Optional[str]:

        # --------------------------------------------------------
        # Wildcard imports are intentionally not resolved.
        # --------------------------------------------------------

        if import_info.is_wildcard:

            return None

        # --------------------------------------------------------
        # from module import function
        #
        #     from calculator import calculate
        #
        # becomes:
        #
        #     calculator::calculate
        # --------------------------------------------------------

        if import_info.is_from_import:

            if import_info.imported_name is None:
                return None

            module_name = self._resolve_relative_module(
                import_info
            )

            candidate = (
                f"{module_name}::"
                f"{import_info.imported_name}"
            )

            if candidate in (
                self.functions_by_qualified_name
            ):

                return candidate

            return None

        # --------------------------------------------------------
        # import calculator
        #
        # The bound name "calculator" represents the module.
        # --------------------------------------------------------

        module_name = self._resolve_relative_module(
            import_info
        )

        if module_name in self.modules_by_name:

            return module_name

        return None

    # ============================================================
    # MODULE ALIAS RESOLUTION
    # ============================================================

    def _resolve_module_alias(
        self,
        file_path: str,
        caller: str,
        qualifier: str,
    ) -> Optional[str]:

        scopes = self._caller_scope_chain(
            caller
        )

        for scope in reversed(scopes):

            import_info = self.imports_by_scope.get(
                (
                    file_path,
                    scope,
                    qualifier,
                )
            )

            if import_info is None:
                continue

            if import_info.is_from_import:
                continue

            module_name = self._resolve_relative_module(
                import_info
            )

            if module_name in self.modules_by_name:

                return module_name

        # A direct module name may not need an explicit import
        # in some malformed/incomplete code, but we only accept
        # it when it actually exists in the project.

        if qualifier in self.modules_by_name:

            return qualifier

        return None

    # ============================================================
    # RELATIVE IMPORTS
    # ============================================================

    def _resolve_relative_module(
        self,
        import_info: ImportInfo,
    ) -> str:

        if import_info.relative_level == 0:
            return import_info.module

        # Find the module containing the import.
        current_module = self._module_for_file(
            import_info.file_path
        )

        if current_module is None:
            return import_info.module

        parts = current_module.split(".")

        # Determine whether this import comes from __init__.py.
        module_info = next(
            (
                module
                for module in self.analysis.modules
                if module.file_path == import_info.file_path
            ),
            None,
        )

        remove_count = import_info.relative_level

        # __init__.py represents the package itself,
        # so we must not remove the package name.
        if module_info is not None and module_info.is_package_init:
            base_parts = parts
        else:
            base_parts = parts[:-1]

        if remove_count > len(base_parts):
            base_parts = []
        else:
            base_parts = base_parts[
                : len(base_parts) - remove_count + 1
            ]

        if import_info.module:
            base_parts.extend(
                import_info.module.split(".")
            )

        return ".".join(
            part
            for part in base_parts
            if part
        )

    # ============================================================
    # SCOPE HELPERS
    # ============================================================

    @staticmethod
    def _caller_scope_chain(
        caller: str,
    ) -> list[str]:

        parts = caller.split("::")

        module_name = parts[0]

        scopes = ["<module>"]

        # Remove module name and caller function name.
        scope_parts = parts[1:-1]

        for index in range(1, len(scope_parts) + 1):
            scopes.append(
                "::".join(scope_parts[:index])
            )
        return scopes

    @staticmethod
    def _module_name_from_call(
        caller: str,
    ) -> str:

        return caller.split("::")[0]

    def _module_for_file(
        self,
        file_path: str,
    ) -> Optional[str]:

        for module in self.analysis.modules:

            if module.file_path == file_path:

                return module.module_name

        return None

    @staticmethod
    def _qualifier_matches_class(
        qualifier: str,
        function: FunctionInfo,
    ) -> bool:

        parts = function.qualified_name.split("::")

        if len(parts) < 3:
            return False

        class_name = parts[-2]

        return qualifier == class_name


# ================================================================
# PUBLIC API
# ================================================================

def build_call_graph(
    analysis: ProjectAnalysis,
) -> CallGraphResult:

    builder = CallGraphBuilder(
        analysis
    )

    return builder.build()


# ================================================================
# MANUAL TEST
# ================================================================

if __name__ == "__main__":

    from core.ast_parser import analyze_project

    analysis = analyze_project(
        "sample_project"
    )

    result = build_call_graph(
        analysis
    )

    print("CALL GRAPH")
    print("=" * 60)

    print(
        f"Nodes: {result.graph.number_of_nodes()}"
    )

    print(
        f"Edges: {result.graph.number_of_edges()}"
    )

    print()

    print("RESOLVED CALLS")
    print("-" * 60)

    if result.resolved_calls:

        for call in result.resolved_calls:

            print(
                f"{call.caller}"
                f" -> "
                f"{call.callee}"
                f" [line {call.line}]"
            )

    else:

        print("None")

    print()

    print("UNRESOLVED CALLS")
    print("-" * 60)

    if result.unresolved_calls:

        for call in result.unresolved_calls:

            print(
                f"{call.caller}"
                f" -> "
                f"{call.expression}"
                f" [line {call.line}]"
                f" | {call.reason}"
            )

    else:

        print("None")

    print()

    print("GRAPH")
    print("-" * 60)

    for caller, callee in result.graph.edges:

        print(
            f"{caller} -> {callee}"
        )