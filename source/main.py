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


# =========================
# Pretty printing helpers
# =========================
def bar(char: str = "─", n: int = 60):
    print(char * n)


def header(text: str):
    print(f"\n\n{Color.BLUE}{Color.BOLD}{text}{Color.RESET}")
    bar()


def kv(key: str, val: str, w: int = 18):
    print(f"{Color.CYAN}{key:<{w}}{Color.RESET}: {val}")


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
            line = line.split('#')[0].strip()  # Remove comments
            if not line:
                continue

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
    """
    Resolve PNML path with priorities:
    1) user_path as-is (absolute or relative to current working directory)
    2) relative to script folder (souce/)
    3) relative to sibling folder: <project_root>/Standard PNMLs/
    4) if user_path is only a filename, walk Standard PNMLs/ to find it
    """
    if not user_path:
        return None

    # 1) As provided (absolute OR relative to CWD)
    if os.path.exists(user_path):
        return os.path.abspath(user_path)

    # Script folder (where this .py is): .../souce
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 2) Relative to script_dir
    cand = os.path.join(script_dir, user_path)
    if os.path.exists(cand):
        return os.path.abspath(cand)

    # Project root is parent of souce/
    project_root = os.path.dirname(script_dir)

    # 3) Sibling folder: Standard PNMLs
    pnml_root = os.path.join(project_root, "Standard PNMLs")
    cand = os.path.join(pnml_root, user_path)
    if os.path.exists(cand):
        return os.path.abspath(cand)

    # 4) If user_path is just a filename, walk Standard PNMLs recursively
    is_filename_only = not any(sep in user_path for sep in ("/", "\\"))
    if is_filename_only and os.path.isdir(pnml_root):
        target = user_path.lower()
        for dirpath, _, filenames in os.walk(pnml_root):
            for fn in filenames:
                if fn.lower() == target:
                    return os.path.abspath(os.path.join(dirpath, fn))

    return None


def run_task_1(net, pnml_path):
    print(f"\n{Color.BOLD}=== TASK 1: PARSING PNML ==={Color.RESET}")
    if net.is_valid:
        print(f"{Color.GREEN}✅ Petri Net consistency check successfully.{Color.RESET}")
        pn_parser.print_petrinet_info(net)


def run_task_2(net, method='bfs'):
    print(f"\n{Color.BOLD}=== TASK 2: EXPLICIT REACHABILITY ==={Color.RESET}")

    methods_to_run = ['bfs', 'dfs'] if method == 'both' else [method]

    for m in methods_to_run:
        if m == 'bfs':
            bfs_markings = reachability.reachable_markings_bfs(net)
            reachability.print_reachability(net, bfs_markings, method_name="bfs")

        elif m == 'dfs':
            dfs_markings = reachability.reachable_markings_dfs(net)
            reachability.print_reachability(net, dfs_markings, method_name="dfs")


def run_task_3(net):
    print(f"\n{Color.BOLD}=== TASK 3: SYMBOLIC REACHABILITY (BDD) ==={Color.RESET}")

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

    # 3. SYMBOLIC BDD
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

    # PRINT BDD FUNCTION
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


def run_task_4(net):
    print(f"\n{Color.BOLD}=== TASK 4: DEADLOCK DETECTION ==={Color.RESET}")

    # Populate transition mapping required for trace printing
    net.transition_id_to_name = {t_id: t_obj.name for t_id, t_obj in net.transitions.items()}

    # --- STEP 1: SYMBOLIC REACHABILITY (TASK 3) ---
    print(f"\n{Color.BOLD}STEP 1: COMPUTING REACHABILITY (BDD){Color.RESET}")
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

    # Empty check (comparison with False node)
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


def run_task_5(net, bdd_data, weight_str):
    print(f"\n{Color.BOLD}=== TASK 5: OPTIMIZATION ==={Color.RESET}")

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

    # Always re-run symbolic search to ensure independence and fresh BDD
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
    print(f"\n{Color.CYAN}--- 5. Running Symbolic Optimization (Exhaustive Method) ---{Color.RESET}")
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

        print("\n--- Best Markings ---")
        groups = reachability.auto_group_places(net)

        # Limit print to 10
        limit = 10
        for i, sol in enumerate(opt_sym_solutions[:limit]):
            vec = []
            for pid in place_order:
                var = f"x_{pid}"
                # Convert dict value (True/False or 1/0) to integer 1/0
                val = 1 if sol.get(var) else 0
                vec.append(val)

            print(f"{Color.YELLOW}Option {i + 1}:{Color.RESET}")
            print(reachability.pretty_marking_vec(tuple(vec), net, place_order, groups))
            print("-" * 40)

        if len(opt_sym_solutions) > limit:
            print(f"... and {len(opt_sym_solutions) - limit} more optimal markings.")

    else:
        print(f"❌ FAIL: Mismatch! Explicit={opt_exp_score}, Symbolic={opt_sym_score}")


def prompt(msg: str, default: str = None, allow_empty: bool = False) -> str:
    """Prompt user for input with optional default."""
    if default is not None:
        full = f"{msg} [{default}]: "
    else:
        full = f"{msg}: "
    while True:
        s = input(full).strip()
        if not s and default is not None:
            return default
        if not s and allow_empty:
            return ""
        if s:
            return s
        print(f"{Color.RED}❌ Input cannot be empty.{Color.RESET}")


def parse_tasks_input(s: str) -> List[int]:
    s = s.strip().lower()
    if s == "all":
        return [1, 2, 3, 4, 5]
    parts = [p.strip() for p in s.split(",") if p.strip()]
    tasks = []
    for p in parts:
        try:
            v = int(p)
        except ValueError:
            raise ValueError("Tasks must be numbers (1-5) or 'all'.")
        if v < 1 or v > 5:
            raise ValueError("Task IDs must be in range 1..5.")
        tasks.append(v)
    return sorted(list(set(tasks)))


def find_pnml_files(base_dir: str, search_subdirs: List[str] = None) -> List[str]:
    """Search for .pnml files under base_dir (or selected subfolders). Return relative paths."""
    if search_subdirs is None:
        roots = [base_dir]
    else:
        roots = [os.path.join(base_dir, d) for d in search_subdirs]

    results = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fn.lower().endswith(".pnml"):
                    abs_path = os.path.join(dirpath, fn)
                    rel_path = os.path.relpath(abs_path, base_dir)
                    results.append(rel_path)
    results.sort()
    return results


def print_run_guide(base_dir: str, std_pnml_dir: str):
    header("PETRI NET TOOL — RUN GUIDE")

    print("Run:")
    print(f"  {Color.YELLOW}python main.py <config_file>.txt{Color.RESET}   (config file mode)")
    print(f"  {Color.YELLOW}python main.py{Color.RESET}                     (interactive mode)")
    print(f"{Color.CYAN}Note:{Color.RESET} config file name is flexible (not required to be 'input.txt').")
    bar()

    kv("Script folder", base_dir)
    kv("PNML folder", std_pnml_dir)
    bar()

    print("Config file format (lines 'key: value'):")
    print("  • pnml: <path or filename>")
    print("  • task: all  (or 1,2,3,4,5)")
    print("  • explicit method: bfs|dfs|both   (optional)")
    print("  • weight vector: ...             (optional)")
    bar()

    print("PNML path can be:")
    print("  • Absolute path: /home/user/models/a.pnml")
    print("  • Relative inside Standard PNMLs: sub/a.pnml")
    print("  • Filename only: a.pnml (auto-search in Standard PNMLs)")
    bar()

    print("Tasks:")
    print("  • 1 = Parse")
    print("  • 2 = Explicit Reachability")
    print("  • 3 = Symbolic(BDD)")
    print("  • 4 = Deadlock")
    print("  • 5 = Optimization")
    print("Explicit method (Task 2): bfs / dfs / both")
    bar()


def interactive_config(std_pnml_dir: str) -> Dict[str, Any]:
    """Ask user for configuration interactively (same flow as main2.py)."""
    header("INTERACTIVE MODE")
    print("You will enter the configuration directly in the terminal (no <config_file>.txt required).")

    # Optional: choose where to scan for PNML files
    print("\nPNML discovery:")
    print("  • I can scan for .pnml files and show suggestions.")
    scan_choice = prompt("Scan for PNML files? (y/n)", default="y").lower()

    suggestions = []
    if scan_choice in ("y", "yes"):
        # Scan Standard PNMLs folder (and common subfolders if present)
        candidates = ["models", "pnml", "data", "examples"]
        suggestions = find_pnml_files(std_pnml_dir, search_subdirs=candidates)
        if not suggestions:
            # Fallback: scan the entire Standard PNMLs
            suggestions = find_pnml_files(std_pnml_dir)

        if suggestions:
            header(f"PNML FILES FOUND: {len(suggestions)} (showing up to 15)")
            for i, rel in enumerate(suggestions[:15], start=1):
                print(f"  {Color.YELLOW}{i:>2}.{Color.RESET} {rel}")
            if len(suggestions) > 15:
                print(f"  ... and {len(suggestions) - 15} more")
            print(f"{Color.CYAN}Tip:{Color.RESET} type the index (e.g., 1) or type a path.\n")
        else:
            print(f"{Color.YELLOW}⚠️ No .pnml files found by scanning 'Standard PNMLs'.{Color.RESET}")

    pnml_in = prompt("Enter PNML file path (or index from the list above)")
    # If user typed an index, map to suggestion
    if pnml_in.isdigit() and suggestions:
        idx = int(pnml_in)
        if 1 <= idx <= len(suggestions):
            pnml_in = suggestions[idx - 1]
            print(f"Selected: {Color.GREEN}{pnml_in}{Color.RESET}")

    tasks_raw = prompt("Select tasks (all or comma-separated 1-5)", default="all")
    while True:
        try:
            tasks = parse_tasks_input(tasks_raw)
            break
        except ValueError as e:
            print(f"{Color.RED}❌ {e}{Color.RESET}")
            tasks_raw = prompt("Re-enter tasks", default="all")

    weight_str = prompt("Enter weight vector (press Enter for Auto)", default="", allow_empty=True).strip()
    method = prompt("Select explicit method (bfs/dfs/both)", default="bfs").strip().lower()
    if method not in ["bfs", "dfs", "both"]:
        print(f"{Color.YELLOW}⚠️ Unknown explicit method '{method}', defaulting to 'bfs'.{Color.RESET}")
        method = "bfs"

    return {
        "pnml": pnml_in,
        "tasks": tasks,
        "weights": weight_str if weight_str else None,
        "explicit_method": method
    }


def main():
    # Keep backward compatibility: optional input.txt
    parser = argparse.ArgumentParser(description="Petri Net Tool: Integrated Runner")
    parser.add_argument("input_file", nargs="?", default=None, help="Path to <config_file>.txt config file (optional)")
    args = parser.parse_args()

    # base_dir = folder chứa main (souce/)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    std_pnml_dir = os.path.join(project_root, "Standard PNMLs")

    print_run_guide(base_dir, std_pnml_dir)

    # --- Load config: file mode or interactive mode ---
    if args.input_file:
        config = parse_config_file(args.input_file)
    else:
        config = interactive_config(std_pnml_dir)

    # --- Resolve PNML path ---
    pnml_raw = config.get("pnml")
    if not pnml_raw:
        print(f"{Color.RED}❌ Error: Missing 'pnml' configuration.{Color.RESET}")
        sys.exit(1)

    pnml_path = resolve_path(pnml_raw)

    # If interactive returned a path relative to Standard PNMLs, ensure it's resolved
    if not pnml_path and os.path.isdir(std_pnml_dir):
        cand = os.path.join(std_pnml_dir, pnml_raw)
        if os.path.exists(cand):
            pnml_path = os.path.abspath(cand)

    if not pnml_path:
        print(f"{Color.RED}❌ Error: PNML file '{pnml_raw}' not found.{Color.RESET}")
        print(f"Hint: Standard PNMLs folder is:\n  {std_pnml_dir}")
        print("Try an absolute path, or a relative path inside 'Standard PNMLs', or just a filename.")
        sys.exit(1)

    # --- Print configuration summary ---
    tasks = sorted(list(set(config.get("tasks", []))))
    if not tasks:
        print(f"{Color.YELLOW}⚠️ No tasks selected. Defaulting to ALL (1-5).{Color.RESET}")
        tasks = [1, 2, 3, 4, 5]

    header("CONFIGURATION")
    kv("Model (PNML)", pnml_path)
    kv("Tasks", ", ".join(map(str, tasks)))
    kv("Weights", config['weights'] if config.get('weights') else "Auto")
    kv("Method", config.get('explicit_method', 'bfs').upper())
    bar()
    print("")

    # --- Parse net once ---
    net = pn_parser.parse_pnml(pnml_path)
    if not net:
        sys.exit(1)

    bdd_S = None
    bdd_mgr = None

    # --- Run tasks ---
    if 1 in tasks:
        run_task_1(net, pnml_path)

    if 2 in tasks:
        run_task_2(net, config.get("explicit_method", "bfs"))

    if 3 in tasks:
        bdd_S, bdd_mgr = run_task_3(net)

    if 4 in tasks:
        run_task_4(net)

    if 5 in tasks:
        run_task_5(net, (bdd_S, bdd_mgr), config.get("weights"))

    print("")
    bar()
    print(f"{Color.GREEN}{Color.BOLD}✅ ALL TASKS COMPLETED{Color.RESET}")
    bar()


if __name__ == "__main__":
    main()
