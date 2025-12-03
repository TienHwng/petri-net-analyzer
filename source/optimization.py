import argparse
import os
import sys
import time
from typing import Dict, Generator, List, Tuple

# --- Import from your existing modules ---
try:
    from parser import PetriNet, parse_pnml

    # Import explicit search and grouping tools
    from reachability import (
        Color,
        auto_group_places,
        build_place_index,
        pretty_marking_vec,
        reachable_markings_bfs,
    )

    # Import symbolic search engine
    from symbolic_computation_BDD import BDD, run_symbolic_search_pure

except ImportError as e:
    print(f"Import Error: {e}")
    print(
        "Ensure parser.py, reachability.py, and symbolic_computation_BDD.py are in the same folder."
    )
    sys.exit(1)


# =============================================================
# 1. HELPER: TRULY AGNOSTIC WEIGHT ASSIGNMENT
# =============================================================
def auto_assign_weights(net: PetriNet) -> Dict[str, int]:
    """
    Automatically discovers place categories from the PNML file
    and assigns weights hierarchically (100, 10, 1, 0).
    """
    groups = auto_group_places(net)
    weights = {}

    print(
        f"{Color.CYAN}--- Automatic Weight Assignment ---{Color.RESET}"
    )

    discovered_categories = sorted([g for g in groups.keys() if g != "Misc"])

    if not discovered_categories:
        print("   No distinct naming patterns found. Treating all as one group.")
        discovered_categories = ["Misc"]

    print(f"   Found {len(discovered_categories)} categories: {discovered_categories}")

    current_weight = 100

    for gname in discovered_categories:
        print(f"   Category '{gname}' -> Assigned Weight: {current_weight}")

        for pid in groups[gname]:
            p_name = net.places[pid].name
            weights[p_name] = current_weight

        if current_weight > 1:
            current_weight //= 10
        else:
            current_weight = 0

    if "Misc" in groups and "Misc" not in discovered_categories:
        print(f"   Category 'Misc' -> Assigned Weight: {current_weight}")
        for pid in groups["Misc"]:
            p_name = net.places[pid].name
            if p_name not in weights:
                weights[p_name] = current_weight

    return weights


# =============================================================
# 2. EXPLICIT OPTIMIZATION
# =============================================================
def solve_optimization_explicit(
    markings_vecs: List[Tuple[int, ...]],
    place_order: List[str],
    place_weights: Dict[str, int],
    net: PetriNet,
) -> Tuple[int, List[Tuple[int, ...]], float]:
    """
    Finds ALL markings that maximize c^T * M using the explicit list.
    Returns: (max_score, list_of_best_markings, time)
    """
    start_time = time.perf_counter()

    max_score = -float("inf")
    best_markings = []

    # Pre-compute weights for indices to speed up the loop
    index_weights = []
    for pid in place_order:
        p_name = net.places[pid].name
        w = place_weights.get(p_name, 0)
        index_weights.append(w)

    for m_vec in markings_vecs:
        current_score = 0
        # Vector dot product
        for i, token_count in enumerate(m_vec):
            if token_count > 0:
                current_score += index_weights[i] * token_count

        if current_score > max_score:
            max_score = current_score
            best_markings = [m_vec]  # Found new max, reset list
        elif current_score == max_score:
            best_markings.append(m_vec)  # Found equal max, add to list

    end_time = time.perf_counter()
    return max_score, best_markings, end_time - start_time


# =============================================================
# 3. SYMBOLIC OPTIMIZATION HELPER (BDD TRAVERSAL)
# =============================================================
def bdd_pick_iter(bdd: BDD, u: int) -> Generator[Dict[str, int], None, None]:
    """
    A generator that yields satisfying assignments (solutions).
    """
    if u == 0:
        return
    if u == 1:
        yield {}
        return

    lvl, low, high = bdd.nodes[u]
    var_name = bdd.level2var[lvl]

    # 1. Traverse High (var = 1)
    for sol in bdd_pick_iter(bdd, high):
        sol[var_name] = 1
        yield sol

    # 2. Traverse Low (var = 0)
    for sol in bdd_pick_iter(bdd, low):
        sol[var_name] = 0
        yield sol


def solve_optimization_symbolic(
    bdd_instance: BDD, reached_node: int, place_weights: Dict[str, int], net: PetriNet
) -> Tuple[int, List[Dict[str, int]], float]:
    """
    Finds ALL max score markings by iterating BDD solutions.
    Returns: (max_score, list_of_best_solutions, time)
    """
    start_time = time.perf_counter()

    max_score = -float("inf")
    best_solutions = []

    # Pre-map: Variable Name (x_ID) -> Weight
    var_weight_map = {}
    for pid, place in net.places.items():
        # Do not sanitize, match raw IDs from symbolic_computation_BDD.py
        var_name = f"x_{pid}"
        w = place_weights.get(place.name, 0)
        var_weight_map[var_name] = w

    # Iterate through paths in the BDD
    for sol in bdd_pick_iter(bdd_instance, reached_node):
        current_score = 0

        for var, val in sol.items():
            if val == 1 and var in var_weight_map:
                current_score += var_weight_map[var]

        if current_score > max_score:
            max_score = current_score
            best_solutions = [sol]  # Reset list
        elif current_score == max_score:
            best_solutions.append(sol)  # Append

    end_time = time.perf_counter()
    return max_score, best_solutions, end_time - start_time


# =============================================================
# 4. MAIN EXECUTION
# =============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Task 5: Optimization over Reachability"
    )
    parser.add_argument(
        "--model", type=str, default="../Standard PNMLs/DocAndPatient.pnml"
    )
    args = parser.parse_args()

    # --- Load Model ---
    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

    print(f"{Color.GREEN}📂 Loading: {pnml_path}{Color.RESET}")
    net = parse_pnml(pnml_path)
    if not net:
        sys.exit(1)

    # --- Define Objective Function (Automatically) ---
    print(
        f"\n{Color.YELLOW}--- 1. Auto-Assigning Objective Function (c^T * M) ---{Color.RESET}"
    )
    weights = auto_assign_weights(net)

    # --- Run Explicit Search ---
    print(f"\n{Color.YELLOW}--- 2. Running Explicit Search (BFS) ---{Color.RESET}")
    bfs_markings = reachable_markings_bfs(net)
    print(f"   Explicit found {len(bfs_markings)} reachable markings.")

    # --- Run Symbolic Search ---
    print(f"\n{Color.YELLOW}--- 3. Running Symbolic Search (BDD) ---{Color.RESET}")
    bdd_cnt, _, _, bdd_S, bdd_mgr = run_symbolic_search_pure(net)
    print(f"   Symbolic found {bdd_cnt} reachable markings.")

    # --- Run Explicit Optimization ---
    print(f"\n{Color.CYAN}--- 4. Running Explicit Optimization ---{Color.RESET}")
    place_order, _ = build_place_index(net)

    opt_exp_score, opt_exp_markings, opt_exp_time = solve_optimization_explicit(
        bfs_markings, place_order, weights, net
    )
    print(f"   Max Score: {opt_exp_score}")
    print(f"   Count of optimal markings: {len(opt_exp_markings)}")
    print(f"   Time: {opt_exp_time:.6f}s")

    # --- Run Symbolic Optimization ---
    print(f"\n{Color.CYAN}--- 5. Running Symbolic Optimization ---{Color.RESET}")
    opt_sym_score, opt_sym_solutions, opt_sym_time = solve_optimization_symbolic(
        bdd_mgr, bdd_S, weights, net
    )
    print(f"   Max Score: {opt_sym_score}")
    print(f"   Count of optimal markings: {len(opt_sym_solutions)}")
    print(f"   Time: {opt_sym_time:.6f}s")

    # --- Verification & Result ---
    print(f"\n{Color.GREEN}=== FINAL RESULT ==={Color.RESET}")
    if opt_exp_score == opt_sym_score:
        print(f"✅ SUCCESS: Both approaches found Max Score = {opt_exp_score}")
        print(f"   Found {len(opt_exp_markings)} optimal marking(s).")

        print(f"\n--- Best Markings (Showing all {len(opt_exp_markings)}) ---")

        groups = auto_group_places(net)

        for i, marking in enumerate(opt_exp_markings):
            print(f"{Color.YELLOW}Option {i + 1}:{Color.RESET}")
            print(pretty_marking_vec(marking, net, place_order, groups))
            print("-" * 40)

    else:
        print(f"❌ FAIL: Mismatch! Explicit={opt_exp_score}, Symbolic={opt_sym_score}")


if __name__ == "__main__":
    main()
