import argparse
import os
import sys
import time
from typing import Dict, List, Tuple

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
# 3. SYMBOLIC OPTIMIZATION (CORRECT DP ON BDD)
# =============================================================


def get_max_weight_dp(
    bdd: BDD,
    u: int,
    level_weights: List[int],
    suffix_gap: List[int],
    memo: Dict[int, int],
) -> int:
    """
    Recursive DP to find the maximum weight.
    Handles 'Gaps' (skipped variables in BDD) by using precomputed suffix sums.
    """
    # 1. Base Cases
    if u == 0:
        return -float("inf")
    if u == 1:
        return 0
    if u in memo:
        return memo[u]

    # 2. Node Info
    lvl, low, high = bdd.nodes[u]

    # Levels of children nodes (Handle terminal nodes 0/1 which are at 'limit' level)
    lvl_low = bdd.nodes[low][0]
    lvl_high = bdd.nodes[high][0]

    # 3. Calculate Gain from Gaps (skipped levels)
    # If levels are skipped between u and child, we implicitly choose '1' for any
    # skipped variable that has positive weight to maximize score.
    # Gap Gain = Sum of weights in range (lvl+1, child_lvl)
    gain_gap_low = suffix_gap[lvl + 1] - suffix_gap[lvl_low]
    gain_gap_high = suffix_gap[lvl + 1] - suffix_gap[lvl_high]

    # 4. Recurse
    val_low = get_max_weight_dp(bdd, low, level_weights, suffix_gap, memo)
    val_high = get_max_weight_dp(bdd, high, level_weights, suffix_gap, memo)

    # 5. Calculate results for this node
    # Option 1: Go Low (var=0) + Gap Gain
    res_low = -float("inf")
    if val_low != -float("inf"):
        res_low = val_low + gain_gap_low

    # Option 2: Go High (var=1) + Weight of u + Gap Gain
    res_high = -float("inf")
    if val_high != -float("inf"):
        w_u = level_weights[lvl]
        res_high = val_high + w_u + gain_gap_high

    res = max(res_low, res_high)
    memo[u] = res
    return res


def extract_best_solutions(
    bdd, u, level_weights, suffix_gap, memo, path: Dict[str, int]
) -> List[Dict[str, int]]:
    """
    Reconstructs optimal paths based on the DP memo table.
    """
    if u == 0:
        return []
    if u == 1:
        return [path.copy()]

    lvl, low, high = bdd.nodes[u]
    var_name = bdd.level2var[lvl]

    # Children levels
    lvl_low = bdd.nodes[low][0]
    lvl_high = bdd.nodes[high][0]

    target = memo[u]  # The score we must achieve from here
    results = []

    # --- Try Low Branch ---
    # Need to check if Low branch was part of the optimal solution
    val_low = 0 if low == 1 else memo.get(low, -float("inf"))

    if val_low != -float("inf"):
        gain_gap = suffix_gap[lvl + 1] - suffix_gap[lvl_low]
        # If going low + gap gain yields the target score, this branch is optimal
        if (val_low + gain_gap) == target:
            path[var_name] = 0
            results.extend(
                extract_best_solutions(bdd, low, level_weights, suffix_gap, memo, path)
            )
            del path[var_name]

    # --- Try High Branch ---
    val_high = 0 if high == 1 else memo.get(high, -float("inf"))

    if val_high != -float("inf"):
        w_u = level_weights[lvl]
        gain_gap = suffix_gap[lvl + 1] - suffix_gap[lvl_high]
        # If going high + weight + gap gain yields target score, this branch is optimal
        if (val_high + w_u + gain_gap) == target:
            path[var_name] = 1
            results.extend(
                extract_best_solutions(bdd, high, level_weights, suffix_gap, memo, path)
            )
            del path[var_name]

    return results


def solve_optimization_symbolic(
    bdd_mgr: BDD, reached_node: int, place_weights: Dict[str, int], net: PetriNet
) -> Tuple[int, List[Dict[str, int]], float]:
    start_time = time.perf_counter()

    # 1. Prepare Weight Arrays for O(1) access
    # BDD variables are interleaved (x_0, xp_0, x_1...).
    # We map 'x_p' levels to weights, 'xp_p' levels to 0.
    limit = len(bdd_mgr.var2level)  # Total variables (limit level is for True/False)
    level_weights = [0] * limit

    # Map variable names to levels and fill weights
    for var, lvl in bdd_mgr.var2level.items():
        # Check if it is a state variable 'x_' (not 'xp_')
        if var.startswith("x_") and not var.startswith("xp_"):
            # Extract real name: x_PlaceID -> PlaceID
            pid = var[2:]
            p_name = net.places[pid].name
            w = place_weights.get(p_name, 0)
            level_weights[lvl] = w

    # 2. Build Suffix Sums for Gap Calculation
    # suffix_gap[i] = sum of weights from level i to end
    suffix_gap = [0] * (limit + 1)
    current_sum = 0
    for i in range(limit - 1, -1, -1):
        # If we skip this level, we assume we pick 1 if weight > 0
        w = max(0, level_weights[i])
        current_sum += w
        suffix_gap[i] = current_sum

    # 3. Handle Root Gap (Optimization)
    # The BDD root 'reached_node' might not be at level 0.
    # Variables before the root are "Don't Care" -> We take max weight.
    root_lvl = bdd_mgr.nodes[reached_node][0]
    prefix_gain = suffix_gap[0] - suffix_gap[root_lvl]

    # 4. Run DP
    memo_scores = {}
    dp_score = get_max_weight_dp(
        bdd_mgr, reached_node, level_weights, suffix_gap, memo_scores
    )

    max_score = dp_score + prefix_gain

    # 5. Extract Solutions
    partial_solutions = extract_best_solutions(
        bdd_mgr, reached_node, level_weights, suffix_gap, memo_scores, {}
    )

    # 6. Finalize Solutions (Fill in Don't Cares)
    # The extraction returns paths for nodes existing in BDD.
    # We must set "Don't Care" variables (skipped in BDD or prefix) to 1 if they have weight.
    final_solutions = []

    # Identify all variables with positive weight
    vars_with_weight = []
    for var, lvl in bdd_mgr.var2level.items():
        if level_weights[lvl] > 0:
            vars_with_weight.append(var)

    for sol in partial_solutions:
        full_sol = sol.copy()
        # If a weight-bearing variable is missing from solution, it was a "Don't Care" or Gap.
        # To maximize score, we set it to 1.
        for var in vars_with_weight:
            if var not in full_sol:
                full_sol[var] = 1
        final_solutions.append(full_sol)

    end_time = time.perf_counter()
    return max_score, final_solutions, end_time - start_time


# =============================================================
# 4. MAIN EXECUTION
# =============================================================
def main():
    parser = argparse.ArgumentParser(description="Task 5: Optimization (Fixed)")
    parser.add_argument(
        "--model", type=str, default="../Standard PNMLs/DocAndPatient.pnml"
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

    # --- Setup ---
    weights = auto_assign_weights(net)
    print(f"\n{Color.YELLOW}--- 2. Running Explicit Search ---{Color.RESET}")
    bfs_markings = reachable_markings_bfs(net)
    print(f"   Explicit found {len(bfs_markings)} reachable markings.")

    print(f"\n{Color.YELLOW}--- 3. Running Symbolic Search ---{Color.RESET}")
    bdd_cnt, _, _, bdd_S, bdd_mgr = run_symbolic_search_pure(net)
    print(f"   Symbolic found {bdd_cnt} reachable markings.")

    # --- Explicit Opt ---
    print(f"\n{Color.CYAN}--- 4. Running Explicit Optimization ---{Color.RESET}")
    place_order, _ = build_place_index(net)
    opt_exp_score, opt_exp_markings, opt_exp_time = solve_optimization_explicit(
        bfs_markings, place_order, weights, net
    )
    print(f"   Max Score: {opt_exp_score}")
    print(f"   Count of optimal markings: {len(opt_exp_markings)}")
    print(f"   Time: {opt_exp_time:.6f}s")

    # --- Symbolic Opt ---
    print(
        f"\n{Color.CYAN}--- 5. Running Symbolic BDD Optimization (DP Method) ---{Color.RESET}"
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

        # Verify Counts
        if len(opt_exp_markings) == len(opt_sym_solutions):
            print(f"✅ SUCCESS: Counts match ({len(opt_sym_solutions)})")
        else:
            print(
                f"⚠️ WARNING: Counts differ (Exp={len(opt_exp_markings)}, Sym={len(opt_sym_solutions)})"
            )
            # Note: This can happen if multiple markings have the same score and 'Don't Care' logic differs slightly,
            # but usually it should match perfectly for 1-safe nets.

        # if len(opt_sym_solutions) > 0 and len(opt_sym_solutions) < 10:
        print("\n--- Best Markings (Symbolic) ---")
        groups = auto_group_places(net)
        for i, sol in enumerate(opt_sym_solutions):
            vec = []
            for pid in place_order:
                var = f"x_{pid}"
                vec.append(sol.get(var, 0))
            print(f"{Color.YELLOW}Option {i + 1}:{Color.RESET}")
            print(pretty_marking_vec(tuple(vec), net, place_order, groups))
            print("-" * 40)
    else:
        print(f"❌ FAIL: Mismatch! Explicit={opt_exp_score}, Symbolic={opt_sym_score}")


if __name__ == "__main__":
    main()
