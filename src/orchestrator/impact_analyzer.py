"""Brownfield Codebase Reasoning and AST Blast-Radius Impact Analyzer."""

import ast
from pathlib import Path
from typing import Dict, List, Set

from src.orchestrator.models import ImpactReport


class CodebaseImpactAnalyzer:
    """Performs AST static analysis to assess blast radius and dependency impacts."""

    def __init__(self, root_dir: str = ".") -> None:
        self.root_dir = Path(root_dir)
        self.symbol_definitions: Dict[str, str] = {}
        self.file_dependencies: Dict[str, Set[str]] = {}
        self.route_endpoints: Dict[str, str] = {}
        self._index_codebase()

    def _index_codebase(self) -> None:
        src_path = self.root_dir / "src"
        if not src_path.exists():
            return

        for py_file in src_path.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.root_dir))
            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=rel_path)
            except Exception:
                continue

            self.file_dependencies[rel_path] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.symbol_definitions[node.name] = rel_path
                elif isinstance(node, ast.FunctionDef):
                    self.symbol_definitions[node.name] = rel_path
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.file_dependencies[rel_path].add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.file_dependencies[rel_path].add(node.module)

    def analyze_proposed_change(
        self,
        modified_files: List[str],
        added_symbols: List[str] = None,
        removed_symbols: List[str] = None,
    ) -> ImpactReport:
        added = added_symbols or []
        removed = removed_symbols or []

        affected_symbols: Set[str] = set()
        impacted_test_files: Set[str] = set()
        is_breaking = len(removed) > 0
        requires_schema_migration = False

        for target_file in modified_files:
            if "database/models.py" in target_file or "models.py" in target_file:
                requires_schema_migration = True

            for sym, fpath in self.symbol_definitions.items():
                if fpath == target_file:
                    affected_symbols.add(sym)

            base_name = Path(target_file).stem
            test_candidates = [
                f"tests/unit/test_{base_name}.py",
                f"tests/integration/test_{base_name}.py",
                "tests/integration/test_api.py",
            ]
            for tc in test_candidates:
                if (self.root_dir / tc).exists():
                    impacted_test_files.add(tc)

        for f in modified_files:
            if "presentation/api.py" in f or "routes.py" in f:
                if removed:
                    is_breaking = True

        total_files = max(1, len(self.file_dependencies))
        blast_score = min(
            1.0,
            round(
                (len(modified_files) / total_files) * 0.5
                + (0.3 if is_breaking else 0.0)
                + (0.2 if requires_schema_migration else 0.0),
                2,
            ),
        )

        summary = (
            f"Impact Analysis: {len(modified_files)} file(s) modified, "
            f"{len(affected_symbols)} symbol(s) affected. "
            f"Breaking Change: {is_breaking}. Schema Migration: {requires_schema_migration}. "
            f"Blast Radius: {blast_score * 100:.0f}%."
        )

        return ImpactReport(
            target_files=modified_files,
            affected_symbols=sorted(list(affected_symbols)),
            is_breaking_change=is_breaking,
            requires_schema_migration=requires_schema_migration,
            impacted_test_files=sorted(list(impacted_test_files)),
            blast_radius_score=blast_score,
            summary=summary,
        )

