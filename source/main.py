import argparse
import os
import sys
import time
import tracemalloc
from typing import Dict, List, Any

# --- Import modules ---
try:
    import parser as pn_parser
    import reachability
    import symbolic_computation_BDD
    import deadlock_detection
    import optimization
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Ensure all python files (parser, reachability, etc.) are in the same folder.")
    sys.exit(1)

class Color:
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

def parse_config_file(filepath: str) -> Dict[str, Any]:
    """Parses input.txt into a dictionary."""
    config = {
        "pnml": None,
        "tasks": [],
        "weights": None,
        "explicit_method": "bfs"  # Default
    }

    if not os.path.exists(filepath):
        print(f"{Color.RED}❌ Error: Input file '{filepath}' not found.{Color.RESET}")
        sys.exit(1)

    with open(filepath, 'r') as f:
        for line in f:
            line = line.split('#')[0].strip() # Remove comments
            if not line: continue

            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key == 'pnml':
                    config['pnml'] = value
                elif key == 'task':
                    if value.lower() == 'all':
                        config['tasks'] = [1, 2, 3, 4, 5]
                    else:
                        try:
                            config['tasks'] = [int(t.strip()) for t in value.split(',')]
                        except ValueError:
                            print(f"{Color.RED}❌ Error: Invalid task format. Use numbers or 'all'.{Color.RESET}")
                            sys.exit(1)
                elif key == 'weight vector':
                    config['weights'] = value
                elif key == 'explicit method':
                    method = value.lower()
                    if method in ['bfs', 'dfs', 'both']:
                        config['explicit_method'] = method
                    else:
                        print(f"{Color.YELLOW}⚠️ Warning: Unknown explicit method '{value}'. Defaulting to 'bfs'.{Color.RESET}")

    return config

def resolve_path(user_path: str) -> str:
    """Resolves relative or absolute paths safely."""
    if os.path.exists(user_path): return user_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    joined_path = os.path.join(base_dir, user_path)
    if os.path.exists(joined_path): return joined_path
    return None

# =============================================================================
# TASK RUNNERS (Replicating "if __name__ == '__main__'" logic of source files)
# =============================================================================

def run_task_1(net, pnml_path):
    print(f"\n{Color.BOLD}=== TASK 1: PARSING PNML ==={Color.RESET}")
    # parser.py main block logic
    # print(f"Parsing file: {pnml_path}")
    # print(f"Validating Petri Net consistency...")
    # (Note: Parsing is already done globally to pass 'net', but we verify info printing)
    if net.is_valid:
        print(f"{Color.GREEN}✅ Petri Net consistency check successfully.{Color.RESET}")
        pn_parser.print_petrinet_info(net)

def run_task_2(net, method='bfs'):
    print(f"\n{Color.BOLD}=== TASK 2: EXPLICIT REACHABILITY ==={Color.RESET}")

    methods_to_run = ['bfs', 'dfs'] if method == 'both' else [method]

    for m in methods_to_run:

        if m == 'bfs':
            bfs_markings = reachability.reachable_markings_bfs(net)
            # Invoke reachability.py's native printer for exact output matching
            reachability.print_reachability(net, bfs_markings, method_name="bfs")

        elif m == 'dfs':
            dfs_markings = reachability.reachable_markings_dfs(net)
            # Invoke reachability.py's native printer for exact output matching
            reachability.print_reachability(net, dfs_markings, method_name="dfs")


def run_task_3(net):
    print(f"\n{Color.BOLD}=== TASK 3: SYMBOLIC REACHABILITY (BDD) ==={Color.RESET}")

    # Replicate symbolic_computation_BDD.py (dd library version)

    # 1. EXPLICIT BFS
    print(f"\n[1] Running EXPLICIT BFS approach (via reachability.py)")
    bfs_cnt, bfs_time, bfs_mem, bfs_list = symbolic_computation_BDD.run_explicit_search(net, 'BFS')
    print(f"   -> Found: {bfs_cnt} markings")
    print(f"   -> Time:  {bfs_time:.6f}s")
    print(f"   -> Mem:   {bfs_mem} bytes")

    # 2. EXPLICIT DFS
    print(f"\n[2] Running EXPLICIT DFS approach (via reachability.py)")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = symbolic_computation_BDD.run_explicit_search(net, 'DFS')
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    # 3. SYMBOLIC BDD (dd library)
    print(f"\n[3] Running SYMBOLIC BDD approach (dd library)")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = symbolic_computation_BDD.run_symbolic_search(net)
    print(f"   -> Found: {bdd_cnt} markings")
    print(f"   -> Time:  {bdd_time:.6f}s")
    print(f"   -> Mem:   {bdd_mem} bytes")

    # COMPARISON
    print("\n=== COMPARISON ===")
    if bfs_cnt == dfs_cnt == bdd_cnt:
        print(f"{Color.GREEN}✅ Result Match!{Color.RESET}")
    else:
        print(f"{Color.RED}❌ Result Mismatch! (BFS:{bfs_cnt}, DFS:{dfs_cnt}, BDD:{bdd_cnt}){Color.RESET}")

    bfs_t = bfs_time if bfs_time > 0 else 1e-9
    dfs_t = dfs_time if dfs_time > 0 else 1e-9

    print(f"Ratio (BDD vs BFS) is {bdd_time / bfs_t:.2f}")
    print(f"Ratio (BDD vs DFS) is {bdd_time / dfs_t:.2f}")

    # PRINT BDD FUNCTION (Expression/DNF depends on adapter)
    print("\n" + "=" * 40)
    print(f"{Color.CYAN}--- SYMBOLIC BDD FUNCTION (Expression Form) ---{Color.RESET}")
    if bdd_cnt <= 50:
        try:
            print(bdd_mgr.to_dnf_string(bdd_S))
        except Exception as e:
            print(f"(Error printing function: {e})")
    else:
        print(f"(Function too complex to print - {bdd_cnt} markings)")
    print("=" * 40)

    # PRINT DETAILED MARKINGS (Explicit BFS)
    print("\n--- [Explicit] Detailed Reachable Markings ---")
    limit_print = 50
    place_order, _ = reachability.build_place_index(net)
    groups = reachability.auto_group_places(net)

    for i, m in enumerate(bfs_list):
        if i >= limit_print:
            print(f"... and {len(bfs_list) - limit_print} more markings.")
            break
        print(f"M{i}:")
        print(reachability.pretty_marking_vec(m, net, place_order, groups))
        print("-" * 30)

    return bdd_S, bdd_mgr

    # 2. EXPLICIT DFS Wrapper
    print(f"\n[2] Running EXPLICIT DFS approach (via reachability.py)")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = symbolic_computation_BDD.run_explicit_wrapper(net, 'DFS')
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    # 3. SYMBOLIC BDD
    print(f"\n[3] Running SYMBOLIC BDD approach")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = symbolic_computation_BDD.run_symbolic_search(net)
    print(f"   -> Found: {bdd_cnt} markings")
    print(f"   -> Time:  {bdd_time:.6f}s")
    print(f"   -> Mem:   {bdd_mem} bytes")

    # COMPARISON
    print("\n=== COMPARISON ===")
    if bfs_cnt == dfs_cnt == bdd_cnt:
        print(f"{Color.GREEN}✅ Result Match!{Color.RESET}")
    else:
        print(f"{Color.RED}❌ Result Mismatch! (BFS:{bfs_cnt}, DFS:{dfs_cnt}, BDD:{bdd_cnt}){Color.RESET}")

    bfs_t = bfs_time if bfs_time > 0 else 1e-9
    dfs_t = dfs_time if dfs_time > 0 else 1e-9

    print(f"Ratio (BDD vs BFS) is {bdd_time / bfs_t:.2f}")
    print(f"Ratio (BDD vs DFS) is {bdd_time / dfs_t:.2f}")

    # PRINT DNF
    print("\n" + "=" * 40)
    print(f"{Color.CYAN}--- SYMBOLIC BDD FUNCTION (DNF Form) ---{Color.RESET}")
    if bdd_cnt <= 1000:
        try:
            print(bdd_mgr.to_dnf_string(bdd_S))
        except Exception as e:
            print(f"(Error printing function: {e})")
    else:
        print(f"(Function too complex to print - {bdd_cnt} markings)")
    print("=" * 40)

    # PRINT DETAILED MARKINGS (Explicit)
    print("\n--- [Explicit] Detailed Reachable Markings ---")
    limit_print = 50
    place_order, _ = reachability.build_place_index(net)
    groups = reachability.auto_group_places(net)

    for i, m in enumerate(bfs_list):
        if i >= limit_print:
            print(f"... and {len(bfs_list) - limit_print} more markings.")
            break
        print(f"M{i}:")
        print(reachability.pretty_marking_vec(m, net, place_order, groups))
        print("-" * 30)

    return bdd_S, bdd_mgr


def run_task_4(net):
    print(f"\n{Color.BOLD}=== TASK 4: DEADLOCK DETECTION ==={Color.RESET}")

    # Populate transition mapping required for trace printing
    net.transition_id_to_name = {t_id: t_obj.name for t_id, t_obj in net.transitions.items()}

    # --- STEP 1: SYMBOLIC REACHABILITY (TASK 3) ---
    print(f"\n{Color.BOLD}STEP 1: COMPUTING REACHABILITY (BDD, dd library){Color.RESET}")
    count, t_reach, mem, S_reach, bdd_mgr = symbolic_computation_BDD.run_symbolic_search(net)
    print(f"   -> Reachable States: {count}")
    print(f"   -> Time: {t_reach:.4f}s")

    # Prepare data for Deadlock Logic
    place_order, _ = reachability.build_place_index(net)
    x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]

    # --- STEP 2: DEADLOCK DETECTION (Intersection) ---
    print(f"\n{Color.BOLD}STEP 2: DEADLOCK DETECTION (Intersection){Color.RESET}")
    start_detect = time.perf_counter()

    Dead_Condition = deadlock_detection.build_dead_formula(bdd_mgr, net, place_order, x_ids)
    Deadlock_Set = bdd_mgr.land(S_reach, Dead_Condition)

    detect_time = time.perf_counter() - start_detect
    print(f"   -> Detection Time: {detect_time:.6f}s")

    # Empty check must use dd.false
    if Deadlock_Set == bdd_mgr.bdd.false:
        print(f"\n{Color.GREEN}✅ CONCLUSION: NO DEADLOCK FOUND.{Color.RESET}")
        print("   The system is deadlock-free.")
        return

    print(f"\n{Color.RED}❌ CONCLUSION: DEADLOCK DETECTED!{Color.RESET}")

    # Extract one deadlock marking using dd.pick()
    dead_marking = deadlock_detection.extract_marking_from_bdd(bdd_mgr, Deadlock_Set, place_order)
    groups = reachability.auto_group_places(net)

    print("\n   [Example Deadlock Marking]:")
    print(reachability.pretty_marking_vec(dead_marking, net, place_order, groups))

    # --- STEP 3: ILP VERIFICATION ---
    deadlock_detection.verify_with_ilp(net, place_order, dead_marking)

    # --- STEP 4: TRACE RECONSTRUCTION ---
    deadlock_detection.find_trace_to_deadlock(net, place_order, dead_marking)

    # --- STEP 1: SYMBOLIC REACHABILITY (TASK 3) ---
    print(f"\n{Color.BOLD}STEP 1: COMPUTING REACHABILITY (BDD){Color.RESET}")

    # Reuse symbolic_computation_BDD logic
    count, t_reach, mem, S_reach, bdd_mgr = symbolic_computation_BDD.run_symbolic_search(net)
    print(f"   -> Reachable States: {count}")
    print(f"   -> BDD Construction Time: {t_reach:.4f}s")

    # Prepare data for Deadlock Logic
    place_order, _ = reachability.build_place_index(net)
    x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]
    var_order = [bdd_mgr.level2var[i] for i in range(len(bdd_mgr.var2level))]

    # --- STEP 2: DEADLOCK DETECTION (LOGIC) ---
    print(f"\n{Color.BOLD}STEP 2: DEADLOCK DETECTION (Intersection){Color.RESET}")

    start_detect = time.perf_counter()

    # 2a. Build Dead Formula (Using function imported from deadlock_detection)
    Dead_Condition = deadlock_detection.build_dead_formula(bdd_mgr, net, place_order, x_ids)

    # 2b. Intersection
    Deadlock_Set = bdd_mgr.land(S_reach, Dead_Condition)

    detect_time = time.perf_counter() - start_detect
    print(f"   -> Detection Time: {detect_time:.6f}s")

    if Deadlock_Set == 0:
        print(f"\n{Color.GREEN}✅ CONCLUSION: NO DEADLOCK FOUND.{Color.RESET}")
        print("   The system is deadlock-free.")
    else:
        print(f"\n{Color.RED}❌ CONCLUSION: DEADLOCK DETECTED!{Color.RESET}")

        # 2c. Extract Example
        dead_marking = deadlock_detection.extract_marking_from_bdd(bdd_mgr, Deadlock_Set, var_order)
        groups = reachability.auto_group_places(net)

        print("\n   [Example Deadlock Marking]:")
        print(reachability.pretty_marking_vec(dead_marking, net, place_order, groups))

        # --- STEP 3: ILP VERIFICATION ---
        deadlock_detection.verify_with_ilp(net, place_order, dead_marking)

        # --- STEP 4: TRACE RECONSTRUCTION ---
        deadlock_detection.find_trace_to_deadlock(net, place_order, dead_marking)


def run_task_5(net, bdd_data, weight_str):
    print(f"\n{Color.BOLD}=== TASK 5: OPTIMIZATION ==={Color.RESET}")

    # Replicate optimization.py main block structure

    # --- 1. Objective Function Setup ---
    print(f"\n{Color.YELLOW}--- 1. Objective Function (c^T * M) ---{Color.RESET}")
    if weight_str:
        weights = optimization.parse_manual_weights(net, weight_str)
    else:
        weights = optimization.auto_assign_weights(net)

    # --- 2. Explicit Search ---
    print(f"\n{Color.YELLOW}--- 2. Running Explicit Search ---{Color.RESET}")
    bfs_markings = reachability.reachable_markings_bfs(net)
    print(f"   Explicit found {len(bfs_markings)} reachable markings.")

    # --- 3. Symbolic Search ---
    print(f"\n{Color.YELLOW}--- 3. Running Symbolic BDD Search ---{Color.RESET}")

    # Always re-run symbolic search to ensure independence and avoid "cached" logic
    bdd_cnt, _, _, bdd_S, bdd_mgr = symbolic_computation_BDD.run_symbolic_search(net)
    print(f"   Symbolic found {bdd_cnt} reachable markings.")

    # --- 4. Explicit Opt ---
    print(f"\n{Color.CYAN}--- 4. Running Explicit Optimization ---{Color.RESET}")
    place_order, _ = reachability.build_place_index(net)
    opt_exp_score, opt_exp_markings, opt_exp_time = optimization.solve_optimization_explicit(
        bfs_markings, place_order, weights, net
    )
    print(f"   Max Score: {opt_exp_score}")
    print(f"   Count of optimal markings: {len(opt_exp_markings)}")
    print(f"   Time: {opt_exp_time:.6f}s")

    # --- 5. Symbolic Opt ---
    print(f"\n{Color.CYAN}--- 5. Running Symbolic Optimization (DP Method) ---{Color.RESET}")
    opt_sym_score, opt_sym_solutions, opt_sym_time = optimization.solve_optimization_symbolic(
        bdd_mgr, bdd_S, weights, net
    )
    print(f"   Max Score: {opt_sym_score}")
    print(f"   Count of optimal markings: {len(opt_sym_solutions)}")
    print(f"   Time: {opt_sym_time:.6f}s")

    # --- Verification & Result ---
    print(f"\n{Color.GREEN}=== FINAL RESULT ==={Color.RESET}")
    if opt_exp_score == opt_sym_score:
        print(f"✅ SUCCESS: Scores match ({opt_exp_score})")
        if len(opt_exp_markings) == len(opt_sym_solutions):
            print(f"✅ SUCCESS: Counts match ({len(opt_sym_solutions)})")
        else:
            print(f"⚠️ WARNING: Counts differ (Exp={len(opt_exp_markings)}, Sym={len(opt_sym_solutions)})")

        print("\n--- Best Markings (Symbolic) ---")
        groups = reachability.auto_group_places(net)
        for i, sol in enumerate(opt_sym_solutions):
            vec = []
            for pid in place_order:
                var = f"x_{pid}"
                vec.append(sol.get(var, 0))
            print(f"{Color.YELLOW}Option {i + 1}:{Color.RESET}")
            print(reachability.pretty_marking_vec(tuple(vec), net, place_order, groups))
            print("-" * 40)
    else:
        print(f"❌ FAIL: Mismatch! Explicit={opt_exp_score}, Symbolic={opt_sym_score}")


def main():
    parser = argparse.ArgumentParser(description="Petri Net Tool: Integrated Runner")
    parser.add_argument("input_file", type=str, help="Path to input.txt config file")
    args = parser.parse_args()

    config = parse_config_file(args.input_file)
    pnml_raw = config['pnml']
    if not pnml_raw:
        print(f"{Color.RED}❌ Error: 'pnml' path missing in input file.{Color.RESET}")
        sys.exit(1)

    pnml_path = resolve_path(pnml_raw)
    if not pnml_path:
        print(f"{Color.RED}❌ Error: PNML file '{pnml_raw}' not found.{Color.RESET}")
        sys.exit(1)

    tasks = sorted(list(set(config['tasks'])))
    print(f"{Color.BLUE}--- CONFIGURATION ---{Color.RESET}")
    print(f"Model: {pnml_path}")
    print(f"Tasks: {tasks}")
    print(f"Weights: {config['weights'] if config['weights'] else 'Auto'}")
    print(f"Explicit Method: {config['explicit_method'].upper()}")
    print("-" * 30)

    # Global parsing for shared usage
    net = pn_parser.parse_pnml(pnml_path)
    if not net: sys.exit(1)

    bdd_S = None
    bdd_mgr = None

    if 1 in tasks:
        run_task_1(net, pnml_path)

    if 2 in tasks:
        run_task_2(net, config['explicit_method'])

    if 3 in tasks:
        bdd_S, bdd_mgr = run_task_3(net)

    if 4 in tasks:
        run_task_4(net)

    if 5 in tasks:
        run_task_5(net, (bdd_S, bdd_mgr), config['weights'])

    print(f"\n{Color.GREEN}=== ALL TASKS COMPLETED ==={Color.RESET}")


if __name__ == "__main__":
    main()