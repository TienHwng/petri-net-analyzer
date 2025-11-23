# # =============================================================
# # reachability.py
# # Task 2: Explicit computation of reachable markings (BFS + DFS)
# # Author: Your Group - MM-251 Assignment (CO2011)
# # =============================================================

# import os
# import argparse
# from collections import deque
# from typing import Dict, List, Tuple
# from parser import parse_pnml, PetriNet
# import re


# # =============================================================
# # ANSI color helpers
# # =============================================================
# class Color:
#     GREEN = "\033[92m"
#     RED = "\033[91m"
#     CYAN = "\033[96m"
#     YELLOW = "\033[93m"
#     RESET = "\033[0m"


# # =============================================================
# # Utility functions
# # =============================================================
# def is_enabled(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> bool:
#     """Check whether a transition is enabled."""
#     if trans_id not in net.input_arcs:
#         return False

#     for place_id, weight in net.input_arcs[trans_id]:
#         if marking.get(place_id, 0) < weight:
#             return False
#     return True


# def fire_transition(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> Dict[str, int]:
#     """Return the new marking after firing a transition."""
#     new_marking = marking.copy()

#     # Remove tokens from input places
#     for place_id, weight in net.input_arcs.get(trans_id, []):
#         new_marking[place_id] = max(0, new_marking.get(place_id, 0) - weight)

#     # Add tokens to output places
#     for place_id, weight in net.output_arcs.get(trans_id, []):
#         new_marking[place_id] = new_marking.get(place_id, 0) + weight

#     return new_marking


# def marking_to_tuple(marking: Dict[str, int], place_order: List[str]) -> Tuple[int]:
#     """Convert a marking dict to tuple for hashing in visited set."""
#     return tuple(marking[p] for p in place_order)


# def pretty_marking_by_philosopher(marking: Dict[str, int], net: PetriNet) -> str:
#     """
#     Pretty-print markings grouped by philosopher.
#     Uses "Yes"/"No" for philosophers and "Free"/"Busy" for forks.
#     """
#     phil_states = {}
#     forks = []

#     for pid, val in marking.items():
#         name = net.places[pid].name
#         lname = name.lower()
#         match = re.search(r"(\d+)", name)
#         phil_num = match.group(1) if match else None

#         # Fork display
#         if "fork" in lname:
#             if val == 1:
#                 forks.append(f"{name}: {Color.GREEN}Free{Color.RESET}")
#             else:
#                 forks.append(f"{name}: {Color.RED}Busy{Color.RESET}")

#         # Philosopher states
#         elif phil_num:
#             if phil_num not in phil_states:
#                 phil_states[phil_num] = []
#             status = f"{Color.GREEN}Yes{Color.RESET}" if val == 1 else f"{Color.RED}No{Color.RESET}"
#             if "think" in lname:
#                 phil_states[phil_num].append(f"Phil {phil_num} Thinking: {status}")
#             elif "eat" in lname:
#                 phil_states[phil_num].append(f"Phil {phil_num} Eating: {status}")

#     # Sort philosophers by number
#     lines = []
#     for phil in sorted(phil_states.keys(), key=lambda x: int(x)):
#         lines.append(" | ".join(phil_states[phil]))

#     if forks:
#         lines.append(" | ".join(forks))

#     return "\n".join("   " + line for line in lines)


# # =============================================================
# # BFS-based reachability
# # =============================================================
# def compute_reachable_markings_bfs(net: PetriNet):
#     """Compute all reachable markings using Breadth-First Search (BFS)."""
#     place_order = list(net.places.keys())
#     initial_marking = {pid: p.initial_marking for pid, p in net.places.items()}

#     visited = set()
#     queue = deque([initial_marking])

#     visited.add(marking_to_tuple(initial_marking, place_order))
#     all_markings = [initial_marking]

#     while queue:
#         current = queue.popleft()

#         for trans_id in net.transitions:
#             if is_enabled(net, trans_id, current):
#                 new_mark = fire_transition(net, trans_id, current)
#                 mark_tuple = marking_to_tuple(new_mark, place_order)

#                 if mark_tuple not in visited:
#                     visited.add(mark_tuple)
#                     queue.append(new_mark)
#                     all_markings.append(new_mark)

#     print("\n=== EXPLICIT REACHABILITY (BFS) ===")
#     print(f"Total reachable markings: {len(all_markings)}\n")
#     for i, m in enumerate(all_markings):
#         print(f"M{i}:")
#         print(pretty_marking_by_philosopher(m, net))
#         print()

#     return all_markings


# # =============================================================
# # DFS-based reachability
# # =============================================================
# def compute_reachable_markings_dfs(net: PetriNet):
#     """Compute all reachable markings using Depth-First Search (DFS)."""
#     place_order = list(net.places.keys())
#     initial_marking = {pid: p.initial_marking for pid, p in net.places.items()}

#     visited = set()
#     all_markings = []

#     def dfs(marking: Dict[str, int]):
#         mark_tuple = marking_to_tuple(marking, place_order)
#         visited.add(mark_tuple)
#         all_markings.append(marking)

#         for trans_id in net.transitions:
#             if is_enabled(net, trans_id, marking):
#                 new_mark = fire_transition(net, trans_id, marking)
#                 new_tuple = marking_to_tuple(new_mark, place_order)
#                 if new_tuple not in visited:
#                     dfs(new_mark)

#     dfs(initial_marking)

#     print("\n=== EXPLICIT REACHABILITY (DFS) ===")
#     print(f"Total reachable markings: {len(all_markings)}\n")
#     for i, m in enumerate(all_markings):
#         print(f"M{i}:")
#         print(pretty_marking_by_philosopher(m, net))
#         print()

#     return all_markings


# # =============================================================
# # Main entry
# # =============================================================
# def main():
#     parser = argparse.ArgumentParser(
#         description="Task 2 - Explicit Reachability Analysis (BFS/DFS) for 1-safe Petri Nets"
#     )
#     parser.add_argument(
#         "--model",
#         type=str,
#         default="../Standard PNMLs/diningPhilosophers.pnml",
#         help="Path to the PNML file (relative or absolute)",
#     )
#     parser.add_argument(
#         "--method",
#         choices=["bfs", "dfs", "both"],
#         default="bfs",
#         help="Choose the search method: bfs, dfs, or both (default)",
#     )

#     args = parser.parse_args()

#     base_dir = os.path.dirname(os.path.abspath(__file__))
#     pnml_path = os.path.normpath(os.path.join(base_dir, args.model))

#     print(f"📂 Loading PNML model: {pnml_path}")

#     if not os.path.exists(pnml_path):
#         print(f"{Color.RED}❌ Error: PNML file not found!{Color.RESET}")
#         return

#     net = parse_pnml(pnml_path)
#     if not net:
#         print(f"{Color.RED}❌ Error: Failed to parse PNML file!{Color.RESET}")
#         return

#     if args.method in ["bfs", "both"]:
#         compute_reachable_markings_bfs(net)
#     if args.method in ["dfs", "both"]:
#         compute_reachable_markings_dfs(net)


# if __name__ == "__main__":
#     main()


# =============================================================
# reachability.py
# Universal Petri Net Reachability Analyzer (BFS + DFS)
# Auto-grouped, color-coded output (no hard-coded names)
# =============================================================

import os
import argparse
import re
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
# Core Petri Net utilities
# =============================================================
def is_enabled(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> bool:
    """Return True if a transition can fire under current marking."""
    if trans_id not in net.input_arcs:
        return False
    for place_id, weight in net.input_arcs[trans_id]:
        if marking.get(place_id, 0) < weight:
            return False
    return True


def fire_transition(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> Dict[str, int]:
    """Return new marking after firing a transition."""
    new_marking = marking.copy()
    for place_id, weight in net.input_arcs.get(trans_id, []):
        new_marking[place_id] = max(0, new_marking.get(place_id, 0) - weight)
    for place_id, weight in net.output_arcs.get(trans_id, []):
        new_marking[place_id] = new_marking.get(place_id, 0) + weight
    return new_marking


def marking_to_tuple(marking: Dict[str, int], place_order: List[str]) -> Tuple[int]:
    """Convert marking dict to tuple for hashing in visited set."""
    return tuple(marking[p] for p in place_order)


# =============================================================
# Automatic grouping heuristic
# =============================================================
def auto_group_places(net: PetriNet):
    """
    Automatically group places based on common prefixes or suffixes.
    Works universally for all PNML models (no hard-coded keywords).
    """
    tokenized = {}
    prefix_count, suffix_count = Counter(), Counter()

    # Step 1: tokenize each place name (split by underscores, camel case, numbers)
    for pid, place in net.places.items():
        name = place.name
        # Split by underscores, numbers, or capital letters
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+|[0-9]+", name)
        if not parts:
            parts = [name]
        tokenized[pid] = parts
        if len(parts) >= 2:
            prefix_count[parts[0]] += 1
            suffix_count[parts[-1]] += 1

    # Step 2: identify common prefixes/suffixes (appear > 1 time)
    common_prefixes = {k for k, v in prefix_count.items() if v > 1}
    common_suffixes = {k for k, v in suffix_count.items() if v > 1}

    # Step 3: group places based on prefix/suffix
    groups = defaultdict(list)
    for pid, parts in tokenized.items():
        if parts[0] in common_prefixes:
            groups[parts[0]].append(pid)
        elif parts[-1] in common_suffixes:
            groups[parts[-1]].append(pid)
        else:
            groups["Misc"].append(pid)

    return groups


# =============================================================
# Pretty printer for markings
# =============================================================
def pretty_marking(marking: Dict[str, int], net: PetriNet) -> str:
    """
    Print markings grouped automatically by name pattern.
    Colors:
      - GREEN = token > 0
      - RED   = token = 0
    Format: "PlaceName: value"
    """
    groups = auto_group_places(net)
    lines = []

    # for gname, pids in sorted(groups.items()):
    #     formatted = []
    #     for pid in pids:
    #         val = marking.get(pid, 0)
    #         color = Color.GREEN if val > 0 else Color.RED
    #         formatted.append(f"{net.places[pid].name}: {color}{val}{Color.RESET}")
    #     lines.append(f"   {gname}: " + " | ".join(formatted))

    # Always print "Misc" group first, then others alphabetically
    for gname in sorted(groups.keys(), key=lambda x: (x != "Misc", x)):
        pids = groups[gname]
        formatted = []
        for pid in pids:
            val = marking.get(pid, 0)
            color = Color.GREEN if val > 0 else Color.RED
            formatted.append(f"{net.places[pid].name}: {color}{val}{Color.RESET}")
        lines.append(f"   {gname}: " + " | ".join(formatted))


    return "\n".join(lines)


# =============================================================
# BFS-based reachability
# =============================================================
def compute_reachable_markings_bfs(net: PetriNet):
    """Enumerate all reachable markings using Breadth-First Search (BFS)."""
    place_order = list(net.places.keys())
    initial = {pid: p.initial_marking for pid, p in net.places.items()}

    visited = set()
    queue = deque([initial])
    visited.add(marking_to_tuple(initial, place_order))
    all_markings = [initial]

    while queue:
        current = queue.popleft()
        for trans_id in net.transitions:
            if is_enabled(net, trans_id, current):
                new_m = fire_transition(net, trans_id, current)
                tup = marking_to_tuple(new_m, place_order)
                if tup not in visited:
                    visited.add(tup)
                    queue.append(new_m)
                    all_markings.append(new_m)

    print("\n=== EXPLICIT REACHABILITY (BFS) ===")
    print(f"Total reachable markings: {len(all_markings)}\n")

    for i, m in enumerate(all_markings):
        print(f"M{i}:")
        print(pretty_marking(m, net))
        print()

    return all_markings


# =============================================================
# DFS-based reachability
# =============================================================
def compute_reachable_markings_dfs(net: PetriNet):
    """Enumerate all reachable markings using Depth-First Search (DFS)."""
    place_order = list(net.places.keys())
    initial = {pid: p.initial_marking for pid, p in net.places.items()}

    visited = set()
    all_markings = []

    def dfs(marking: Dict[str, int]):
        tup = marking_to_tuple(marking, place_order)
        visited.add(tup)
        all_markings.append(marking)
        for trans_id in net.transitions:
            if is_enabled(net, trans_id, marking):
                new_m = fire_transition(net, trans_id, marking)
                new_tup = marking_to_tuple(new_m, place_order)
                if new_tup not in visited:
                    dfs(new_m)

    dfs(initial)

    print("\n=== EXPLICIT REACHABILITY (DFS) ===")
    print(f"Total reachable markings: {len(all_markings)}\n")

    for i, m in enumerate(all_markings):
        print(f"M{i}:")
        print(pretty_marking(m, net))
        print()

    return all_markings


# =============================================================
# Main entry
# =============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Universal Reachability Analyzer (auto-grouped, color-coded BFS/DFS) for 1-safe Petri Nets"
    )
    parser.add_argument(
        "--model", type=str, default="F:/MM-251-Assignment/Standard PNMLs/diningPhilosophers.pnml",
        help="Path to PNML file (relative or absolute)"
    )
    parser.add_argument(
        "--method", choices=["bfs", "dfs", "both"], default="bfs",
        help="Search method: bfs, dfs, or both"
    )

    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pnml_path = os.path.normpath(os.path.join(base_dir, args.model))

    print(f"📂 Loading PNML model: {pnml_path}")

    if not os.path.exists(pnml_path):
        print(f"{Color.RED}❌ Error: PNML file not found!{Color.RESET}")
        return

    net = parse_pnml(pnml_path)
    if not net:
        print(f"{Color.RED}❌ Error: Failed to parse PNML file!{Color.RESET}")
        return

    if args.method in ["bfs", "both"]:
        compute_reachable_markings_bfs(net)
    if args.method in ["dfs", "both"]:
        compute_reachable_markings_dfs(net)


if __name__ == "__main__":
    main()
