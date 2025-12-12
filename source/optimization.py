import argparse
import os
import sys
import time
from typing import Any, Dict, List, Tuple

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
    # We import the new 'run_symbolic_search' which returns the dd manager adapter
    from symbolic_computation_BDD import run_symbolic_search

except ImportError as e:
    print(f"Import Error: {e}")
    print(
        "Ensure parser.py, reachability.py, and symbolic_computation_BDD.py are in the same folder."
    )
    sys.exit(1)


# =============================================================
# 1. HELPER: WEIGHT ASSIGNMENT (AUTO & MANUAL)
# =============================================================
def auto_assign_weights(net: PetriNet) -> Dict[str, int]:
    """
    Automatically discovers place categories from the PNML file
    and assigns weights hierarchically (100, 10, 1, 0).
    """
    groups = auto_group_places(net)
    weights = {}

    print(f"{Color.CYAN}--- Automatic Weight Assignment ---{Color.RESET}")

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


def parse_manual_weights(net: PetriNet, weight_str: str) -> Dict[str, int]:
    """
    Parses a string like 'p1=10, p2=5' into a dictionary.
    Validates that place names exist in the net.
    """
    weights = {}
    if not weight_str:
        return weights

    # Build a set of valid place names for validation
    valid_names = {p.name for p in net.places.values()}

    print(f"{Color.CYAN}--- Manual Weight Assignment ---{Color.RESET}")
    entries = weight_str.split(",")

    for entry in entries:
        if "=" not in entry:
            print(
                f"   {Color.RED}⚠️ Warning: Ignoring invalid format '{entry}'. Expected 'Name=Value'.{Color.RESET}"
            )
            continue

        p_name, val_str = entry.split("=", 1)
        p_name = p_name.strip()
        val_str = val_str.strip()

        if p_name not in valid_names:
            print(
                f"   {Color.RED}⚠️ Warning: Place '{p_name}' not found in Petri Net. Ignoring.{Color.RESET}"
            )
            continue

        try:
            val = int(val_str)
            weights[p_name] = val
            print(f"   Place '{p_name}' -> Assigned Weight: {val}")
        except ValueError:
            print(
                f"   {Color.RED}⚠️ Warning: Invalid weight '{val_str}' for '{p_name}'. Expected integer.{Color.RESET}"
            )

    return weights


# =============================================================
# 2. EXPLICIT OPTIMIZATION (BASELINE)
# =============================================================
def solve_optimization_explicit(
    markings_vecs: List[Tuple[int, ...]],
    place_order: List[str],
    place_weights: Dict[str, int],
    net: PetriNet,
) -> Tuple[int, List[Tuple[int, ...]], float]:
    """
    Finds ALL markings that maximize c^T * M using the explicit list.
    """
    start_time = time.perf_counter()

    max_score = -float("inf")
    best_markings = []

    # Pre-compute weights for indices
    index_weights = []
    for pid in place_order:
        p_name = net.places[pid].name
        w = place_weights.get(p_name, 0)
        index_weights.append(w)

    for m_vec in markings_vecs:
        current_score = 0
        for i, token_count in enumerate(m_vec):
            if token_count > 0:
                current_score += index_weights[i] * token_count

        if current_score > max_score:
            max_score = current_score
            best_markings = [m_vec]
        elif current_score == max_score:
            best_markings.append(m_vec)

    end_time = time.perf_counter()
    return max_score, best_markings, end_time - start_time


# =============================================================
# 3. SYMBOLIC OPTIMIZATION (EXHAUSTIVE ITERATION)
# =============================================================
def solve_optimization_symbolic(
    bdd_mgr_adapter, reached_node, place_weights: Dict[str, int], net: PetriNet
) -> Tuple[int, List[Dict[str, int]], float]:
    """
    Solves optimization by EXHAUSTIVELY iterating over all satisfying assignments
    in the BDD (Reach(M0)).
    
    This is conceptually similar to the explicit approach but retrieves markings
    from the BDD structure using the library's iterator.
    """
    start_time = time.perf_counter()

    # Unwrap the 'dd' object from the adapter
    bdd = bdd_mgr_adapter.bdd

    # 1. Reconstruct Variable Order
    # We need to know which BDD variable corresponds to which place to apply weights.
    # The encoding used: "x_{pid}" for current state.
    place_order, _ = build_place_index(net)
    
    # Identify the "care variables" (current state variables)
    # We must tell pick_iter to only care about these, effectively projecting out 'next' vars
    cur_vars = []
    var_to_weight = {}

    for pid in place_order:
        var_name = f"x_{pid}"
        cur_vars.append(var_name)
        
        # Map variable name directly to its weight
        p_name = net.places[pid].name
        w = place_weights.get(p_name, 0)
        var_to_weight[var_name] = w

    # 2. Iterate Exhaustively
    # bdd.pick_iter yields a dictionary for every satisfying assignment.
    # e.g., {'x_p1': 1, 'x_p2': 0, ...}
    
    max_score = -float("inf")
    best_solutions = []
    
    # We iterate over assignments restricted to cur_vars.
    # If the BDD is huge, this loop is the bottleneck (Enumeration Complexity).
    for assignment in bdd.pick_iter(reached_node, care_vars=cur_vars):
        current_score = 0
        
        # Calculate score c^T * M
        for var_name, val in assignment.items():
            if val: # If token is present (True or 1)
                current_score += var_to_weight.get(var_name, 0)
        
        # Check Max
        if current_score > max_score:
            max_score = current_score
            best_solutions = [assignment]
        elif current_score == max_score:
            best_solutions.append(assignment)

    end_time = time.perf_counter()
    
    # If no reachable markings (shouldn't happen for valid nets), handle gracefully
    if max_score == -float("inf"):
        max_score = 0

    return max_score, best_solutions, end_time - start_time


# =============================================================
# 4. MAIN EXECUTION
# =============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Task 5: Optimization over Reachability (dd Library - Exhaustive)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="../Standard PNMLs/diningPhilosophers.pnml",
        help="Path to PNML file",
    )
    parser.add_argument(
        "--weights", type=str, help="Manual weights: 'PlaceA=10,PlaceB=5' (Unlisted=0)"
    )

    args = parser.parse_args()

    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

    print(f"{Color.GREEN}📂 Loading: {pnml_path}{Color.RESET}")
    net = parse_pnml(pnml_path)
    if not net:
        sys.exit(1)

    # --- 1. Objective Function Setup ---
    print(f"\n{Color.YELLOW}--- 1. Objective Function (c^T * M) ---{Color.RESET}")
    if args.weights:
        weights = parse_manual_weights(net, args.weights)
    else:
        weights = auto_assign_weights(net)

    # --- 2. Explicit Search ---
    print(f"\n{Color.YELLOW}--- 2. Running Explicit Search ---{Color.RESET}")
    bfs_markings = reachable_markings_bfs(net)
    print(f"   Explicit found {len(bfs_markings)} reachable markings.")

    # --- 3. Symbolic Search ---
    print(f"\n{Color.YELLOW}--- 3. Running Symbolic Search ---{Color.RESET}")
    # run_symbolic_search returns (cnt, time, mem, reached_node, bdd_adapter)
    bdd_cnt, _, _, bdd_S, bdd_mgr = run_symbolic_search(net)
    print(f"   Symbolic found {bdd_cnt} reachable markings.")

    # --- 4. Explicit Opt ---
    print(f"\n{Color.CYAN}--- 4. Running Explicit Optimization ---{Color.RESET}")
    place_order, _ = build_place_index(net)
    opt_exp_score, opt_exp_markings, opt_exp_time = solve_optimization_explicit(
        bfs_markings, place_order, weights, net
    )
    print(f"   Max Score: {opt_exp_score}")
    print(f"   Count of optimal markings: {len(opt_exp_markings)}")
    print(f"   Time: {opt_exp_time:.6f}s")

    # --- 5. Symbolic Opt ---
    print(
        f"\n{Color.CYAN}--- 5. Running Symbolic Optimization (Exhaustive) ---{Color.RESET}"
    )
    opt_sym_score, opt_sym_solutions, opt_sym_time = solve_optimization_symbolic(
        bdd_mgr, bdd_S, weights, net
    )
    print(f"   Max Score: {opt_sym_score}")
    print(f"   Count of optimal markings: {len(opt_sym_solutions)}")
    print(f"   Time: {opt_sym_time:.6f}s")

    # --- Result ---
    print(f"\n{Color.GREEN}=== FINAL RESULT ==={Color.RESET}")
    if opt_exp_score == opt_sym_score:
        print(f"✅ SUCCESS: Scores match ({opt_exp_score})")

        if len(opt_exp_markings) == len(opt_sym_solutions):
            print(f"✅ SUCCESS: Counts match ({len(opt_sym_solutions)})")
        else:
            print(
                f"⚠️ WARNING: Counts differ (Exp={len(opt_exp_markings)}, Sym={len(opt_sym_solutions)})"
            )

        print("\n--- Best Markings ---")
        groups = auto_group_places(net)

        # Limit print to 10
        for i, sol in enumerate(opt_sym_solutions[:10]):
            vec = []
            for pid in place_order:
                var = f"x_{pid}"
                # Get value from dict, default to 0 (False)
                val = 1 if sol.get(var) else 0
                vec.append(val)
            print(f"{Color.YELLOW}Option {i + 1}:{Color.RESET}")
            print(pretty_marking_vec(tuple(vec), net, place_order, groups))
            print("-" * 40)
        if len(opt_sym_solutions) > 10:
            print(f"... and {len(opt_sym_solutions) - 10} more.")

    else:
        print(f"❌ FAIL: Mismatch! Explicit={opt_exp_score}, Symbolic={opt_sym_score}")


if __name__ == "__main__":
    main()