# =============================================================
# reachability.py
# Universal Petri Net Reachability Analyzer (BFS + DFS)
#  - 1-safe marking representation (0/1 vector)
#  - Clear separation: search vs printing
# =============================================================

import os
import re
import argparse
from collections import deque, defaultdict, Counter
from typing import Dict, List, Tuple

from parser import parse_pnml, PetriNet


# =============================================================
# ANSI color helpers
# =============================================================
class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


# =============================================================
# Marking representation for 1-safe Petri nets
# =============================================================
# Vec = tuple of 0/1 indicating token presence for each place
Vec = Tuple[int, ...]


def build_place_index(net: PetriNet) -> Tuple[List[str], Dict[str, int]]:
    """
    Return a deterministic ordering of places and a map from place_id to index.
    place_order[i] is the place_id for index i in the marking vector.
    """
    # Sorted for deterministic order (avoid dependency on dict insertion order)
    place_order = sorted(net.places.keys())
    pid_to_index = {pid: i for i, pid in enumerate(place_order)}
    return place_order, pid_to_index


def initial_marking_vec(net: PetriNet, place_order: List[str]) -> Vec:
    """
    Build the initial marking as a 0/1 vector (1-safe semantics).
    Any positive initial_marking is treated as 1.
    """
    vec: List[int] = []
    for pid in place_order:
        init_tokens = net.places[pid].initial_marking
        vec.append(1 if init_tokens > 0 else 0)
    return tuple(vec)


def build_indexed_arcs(
    net: PetriNet,
    pid_to_index: Dict[str, int],
) -> Tuple[Dict[str, List[Tuple[int, int]]], Dict[str, List[Tuple[int, int]]]]:
    """
    Convert place-based arcs (using place_id) to index-based arcs.

    Returns
    -------
    pre_arcs : Dict[str, List[Tuple[int, int]]]
        pre_arcs[t] = list of (place_index, weight) for input arcs.
    post_arcs : Dict[str, List[Tuple[int, int]]]
        post_arcs[t] = list of (place_index, weight) for output arcs.
    """
    pre_arcs: Dict[str, List[Tuple[int, int]]] = {}
    post_arcs: Dict[str, List[Tuple[int, int]]] = {}

    # input arcs
    for t_id, arcs in net.input_arcs.items():
        pre_arcs[t_id] = [(pid_to_index[pid], w) for pid, w in arcs]

    # output arcs
    for t_id, arcs in net.output_arcs.items():
        post_arcs[t_id] = [(pid_to_index[pid], w) for pid, w in arcs]

    return pre_arcs, post_arcs


def is_enabled_vec(
    trans_id: str,
    marking: Vec,
    pre_arcs: Dict[str, List[Tuple[int, int]]],
) -> bool:
    """
    Check if a transition is enabled under a given 1-safe marking vector.

    Semantics
    ---------
    - We require marking[idx] >= weight for every (idx, weight) in the preset.
    - If a transition has no entry in pre_arcs, it is considered *not enabled*.
      This means transitions without input places are disabled unless the parser
      stores them with an explicit empty list in net.input_arcs.
      If you prefer the textbook Petri net semantics where an empty preset
      implies "always enabled", you can change this behavior.
    """
    if trans_id not in pre_arcs:
        return False

    for idx, weight in pre_arcs[trans_id]:
        if marking[idx] < weight:
            return False
    return True


def fire_transition_vec(
    trans_id: str,
    marking: Vec,
    pre_arcs: Dict[str, List[Tuple[int, int]]],
    post_arcs: Dict[str, List[Tuple[int, int]]],
) -> Vec:
    """
    Fire a transition and return the new 1-safe marking vector.

    Assumes
    -------
    - is_enabled_vec(trans_id, marking, pre_arcs) returned True.

    Runtime checks
    --------------
    - If consumption would make a place negative, a ValueError is raised.
      (This should never happen if is_enabled_vec is correct.)
    - If any place ends up with more than 1 token, a ValueError is raised
      to signal a violation of 1-safeness.
    """
    if not is_enabled_vec(trans_id, marking, pre_arcs):
        raise ValueError(f"Transition {trans_id} fired while not enabled")

    new = list(marking)

    # consume tokens
    for idx, weight in pre_arcs.get(trans_id, []):
        new[idx] -= weight
        if new[idx] < 0:
            raise ValueError("Negative token count encountered")

    # produce tokens
    for idx, weight in post_arcs.get(trans_id, []):
        new[idx] += weight
        if new[idx] > 1:
            raise ValueError(
                f"1-safe violated: place index {idx} has {new[idx]} tokens"
            )

    return tuple(new)


# =============================================================
# Automatic grouping heuristic (used only for pretty-printing)
# =============================================================
def auto_group_places(net: PetriNet):
    """
    Automatically group places based on common prefixes or suffixes.
    Works as a heuristic: no hard-coded keywords.
    """
    tokenized: Dict[str, List[str]] = {}
    prefix_count, suffix_count = Counter(), Counter()

    # Step 1: tokenize each place name (split by underscores, camel case, numbers)
    for pid, place in net.places.items():
        name = place.name
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+|[0-9]+", name)
        if not parts:
            parts = [name]
        tokenized[pid] = parts
        if len(parts) >= 2:
            prefix_count[parts[0]] += 1
            suffix_count[parts[-1]] += 1

    # Step 2: identify common prefixes/suffixes (appear more than once)
    common_prefixes = {k for k, v in prefix_count.items() if v > 1}
    common_suffixes = {k for k, v in suffix_count.items() if v > 1}

    # Step 3: group places based on prefix/suffix
    groups: Dict[str, List[str]] = defaultdict(list)
    for pid, parts in tokenized.items():
        if parts[0] in common_prefixes:
            groups[parts[0]].append(pid)
        elif parts[-1] in common_suffixes:
            groups[parts[-1]].append(pid)
        else:
            groups["Misc"].append(pid)

    return groups


def pretty_marking_vec(
    marking: Vec,
    net: PetriNet,
    place_order: List[str],
    groups=None,
) -> str:
    """
    Pretty-print a 1-safe marking vector, grouped by name patterns.

    Colors
    ------
    - GREEN = token present (1)
    - RED   = token absent (0)
    """
    if groups is None:
        groups = auto_group_places(net)

    # Map place_id -> index for quick lookup
    pid_to_index = {pid: i for i, pid in enumerate(place_order)}

    lines: List[str] = []

    # Always print "Misc" first, then others alphabetically
    for gname in sorted(groups.keys(), key=lambda x: (x != "Misc", x)):
        pids = groups[gname]
        formatted = []
        for pid in pids:
            idx = pid_to_index[pid]
            val = marking[idx]
            color = Color.GREEN if val > 0 else Color.RED
            formatted.append(
                f"{net.places[pid].name}: {color}{val}{Color.RESET}"
            )
        lines.append(f"   {gname}: " + " | ".join(formatted))

    return "\n".join(lines)


# =============================================================
# Reachability (core algorithms - no printing)
# =============================================================
def reachable_markings_bfs(net: PetriNet) -> List[Vec]:
    """
    Enumerate all reachable markings using Breadth-First Search (BFS).

    Returns
    -------
    List[Vec]
        List of all reachable 1-safe markings (each marking is a Vec).
    """
    place_order, pid_to_index = build_place_index(net)
    pre_arcs, post_arcs = build_indexed_arcs(net, pid_to_index)
    initial = initial_marking_vec(net, place_order)

    visited = {initial}
    queue = deque([initial])
    all_markings: List[Vec] = []

    # transitions may be a dict or an iterable of IDs; list(...) materializes it
    transitions = list(net.transitions)

    while queue:
        current = queue.popleft()
        all_markings.append(current)

        for t_id in transitions:
            if is_enabled_vec(t_id, current, pre_arcs):
                new_m = fire_transition_vec(t_id, current, pre_arcs, post_arcs)
                if new_m not in visited:
                    visited.add(new_m)
                    queue.append(new_m)

    return all_markings


def reachable_markings_dfs(net: PetriNet) -> List[Vec]:
    """
    Enumerate all reachable markings using Depth-First Search (DFS).

    DFS is implemented iteratively (using an explicit stack) to avoid
    Python recursion depth limitations.

    Returns
    -------
    List[Vec]
        List of all reachable 1-safe markings (each marking is a Vec).
    """
    place_order, pid_to_index = build_place_index(net)
    pre_arcs, post_arcs = build_indexed_arcs(net, pid_to_index)
    initial = initial_marking_vec(net, place_order)

    visited = {initial}
    stack = [initial]
    all_markings: List[Vec] = []

    transitions = list(net.transitions)

    while stack:
        current = stack.pop()
        all_markings.append(current)

        for t_id in transitions:
            if is_enabled_vec(t_id, current, pre_arcs):
                new_m = fire_transition_vec(t_id, current, pre_arcs, post_arcs)
                if new_m not in visited:
                    visited.add(new_m)
                    stack.append(new_m)

    return all_markings


# =============================================================
# Printing / CLI layer (I/O only, no core algorithms)
# =============================================================
def print_reachability(
    net: PetriNet,
    markings: List[Vec],
    method_name: str,
) -> None:
    """
    Pretty-print the list of reachable markings computed by BFS/DFS.
    """
    place_order, _ = build_place_index(net)
    groups = auto_group_places(net)

    print(f"\n=== EXPLICIT REACHABILITY ({method_name.upper()}) ===")
    print(f"Total reachable markings: {len(markings)}\n")

    for i, m in enumerate(markings):
        print(f"M{i}:")
        print(pretty_marking_vec(m, net, place_order, groups=groups))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Universal Reachability Analyzer (1-safe, auto-grouped, color-coded BFS/DFS)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="../Standard PNMLs/diningPhilosophers.pnml",
        help="Path to PNML file (relative or absolute)",
    )
    parser.add_argument(
        "--method",
        choices=["bfs", "dfs", "both"],
        default="bfs",
        help="Search method: bfs, dfs, or both",
    )

    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pnml_path = os.path.normpath(os.path.join(base_dir, args.model))

    print(f"{Color.CYAN}📂 Loading PNML model: {pnml_path}{Color.RESET}")

    if not os.path.exists(pnml_path):
        print(f"{Color.RED}❌ Error: PNML file not found!{Color.RESET}")
        return

    net = parse_pnml(pnml_path)
    if net is None:
        print(f"{Color.RED}❌ Error: Failed to parse PNML file!{Color.RESET}")
        return

    if args.method in ["bfs", "both"]:
        bfs_markings = reachable_markings_bfs(net)
        print_reachability(net, bfs_markings, method_name="bfs")

    if args.method in ["dfs", "both"]:
        dfs_markings = reachable_markings_dfs(net)
        print_reachability(net, dfs_markings, method_name="dfs")


if __name__ == "__main__":
    main()