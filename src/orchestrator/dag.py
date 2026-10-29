"""Directed Acyclic Graph (DAG) engine supporting parallel layers and dynamic replanning."""

from collections import defaultdict, deque
from typing import Dict, List, Set

from src.orchestrator.models import TaskNode, TaskStatus


class CyclicDependencyError(Exception):
    """Raised when a dependency cycle is detected in the DAG."""
    pass


class TaskGraph:
    """Directed Acyclic Graph managing task execution order, parallel layers, and re-planning."""

    def __init__(self) -> None:
        self.nodes: Dict[str, TaskNode] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)        # parent -> children
        self.in_degree: Dict[str, Set[str]] = defaultdict(set)    # child -> parents (dependencies)

    def add_node(self, node: TaskNode) -> None:
        """Register a new task node into the graph."""
        self.nodes[node.id] = node
        for dep_id in node.dependencies:
            self.add_edge(dep_id, node.id)

    def add_edge(self, parent_id: str, child_id: str) -> None:
        """Declare that child_id depends on parent_id."""
        self.edges[parent_id].add(child_id)
        self.in_degree[child_id].add(parent_id)

    def detect_cycles(self) -> bool:
        """Verifies that the graph contains no cyclic dependencies."""
        visited: Dict[str, int] = {k: 0 for k in self.nodes}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(node_id: str) -> bool:
            visited[node_id] = 1
            for child in self.edges.get(node_id, set()):
                if visited.get(child, 0) == 1:
                    return True
                if visited.get(child, 0) == 0 and dfs(child):
                    return True
            visited[node_id] = 2
            return False

        for node_id in self.nodes:
            if visited[node_id] == 0:
                if dfs(node_id):
                    return True
        return False

    def get_parallel_layers(self) -> List[List[TaskNode]]:
        """Computes topological execution layers separated by synchronization barriers.
        
        Nodes in the same inner list have all their dependencies satisfied and can execute
        in parallel. Subsequent layers wait for prior layers to synchronize.
        """
        if self.detect_cycles():
            raise CyclicDependencyError("Cycle detected in SDLC task dependency graph.")

        # In-degree count map
        remaining_deps: Dict[str, int] = {
            node_id: len(self.in_degree[node_id]) for node_id in self.nodes
        }

        ready_queue = deque([
            node_id for node_id, count in remaining_deps.items() if count == 0
        ])

        layers: List[List[TaskNode]] = []
        visited_count = 0

        while ready_queue:
            current_layer_ids = list(ready_queue)
            ready_queue.clear()

            current_layer_nodes = [self.nodes[nid] for nid in current_layer_ids]
            layers.append(current_layer_nodes)
            visited_count += len(current_layer_nodes)

            # Decrement dependencies for downstream children
            for nid in current_layer_ids:
                for child_id in self.edges.get(nid, set()):
                    remaining_deps[child_id] -= 1
                    if remaining_deps[child_id] == 0:
                        ready_queue.append(child_id)

        if visited_count != len(self.nodes):
            raise CyclicDependencyError("Unresolvable dependencies in task graph.")

        return layers

    def replan(self, failed_node_id: str, replacement_nodes: List[TaskNode]) -> None:
        """Dynamically replace a failed node and its downstream subgraph with a new plan."""
        # Find all downstream dependents
        downstream: Set[str] = set()

        def collect_downstream(nid: str) -> None:
            for child in self.edges.get(nid, set()):
                if child not in downstream:
                    downstream.add(child)
                    collect_downstream(child)

        collect_downstream(failed_node_id)

        # Invalidate or reset downstream nodes
        for nid in downstream:
            if nid in self.nodes:
                self.nodes[nid].status = TaskStatus.PENDING

        # Mark failed node as rolled back or failed
        if failed_node_id in self.nodes:
            self.nodes[failed_node_id].status = TaskStatus.FAILED

        # Insert replacement nodes
        for r_node in replacement_nodes:
            self.add_node(r_node)

