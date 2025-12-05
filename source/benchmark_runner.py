import os
import sys
import time
import glob
import argparse
import contextlib
import traceback
from typing import List, Dict


# --- Cấu hình hiển thị màu sắc ---
class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"


# --- Import các module ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from parser import parse_pnml
    from reachability import build_place_index
    # Import Task 2 & 3
    from symbolic_computation_BDD import run_symbolic_search, run_explicit_search

    # [1] CODE SYMBOLIC (Của bạn)
    from deadlock_detection import build_dead_formula, extract_marking_from_bdd

    # [2] CODE CEGAR (Để so sánh)
    try:
        from deadlock_detection_cegar import check_deadlock_cegar
    except ImportError:
        check_deadlock_cegar = None
        # Chỉ in warning 1 lần ở đầu
        pass

except ImportError as e:
    print(f"{Color.RED}❌ Lỗi Import: {e}{Color.RESET}")
    print("Hãy đảm bảo các file code nằm cùng thư mục.")
    sys.exit(1)


# =============================================================
# UTILS
# =============================================================
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout


def format_marking(marking_vec: List[int], place_order: List[str], net) -> str:
    if not marking_vec:
        return "N/A"
    active = []
    for i, val in enumerate(marking_vec):
        if val > 0:
            p_id = place_order[i]
            p_obj = net.places.get(p_id)
            name = str(p_obj.name) if p_obj and hasattr(p_obj, "name") and p_obj.name else str(p_id)
            active.append(name)
    return ", ".join(active) if active else "Empty"


# =============================================================
# BENCHMARK ENGINE
# =============================================================

def run_benchmark_on_file(filepath: str):
    filename = os.path.basename(filepath)
    print(f"Processing: {Color.CYAN}{filename:<30}{Color.RESET}", end="\r")

    try:
        net = parse_pnml(filepath)
        if not net:
            return None
        num_places = len(net.places)

        # ---------------------------------------------------------
        # TASK 2: EXPLICIT REACHABILITY
        # ---------------------------------------------------------
        # BFS
        start = time.perf_counter()
        with suppress_stdout():
            bfs_cnt, _, _, _ = run_explicit_search(net, "BFS")
        bfs_time = (time.perf_counter() - start) * 1000

        # DFS
        start = time.perf_counter()
        with suppress_stdout():
            dfs_cnt, _, _, _ = run_explicit_search(net, "DFS")
        dfs_time = (time.perf_counter() - start) * 1000

        # ---------------------------------------------------------
        # TASK 3: SYMBOLIC REACHABILITY (Dùng chung)
        # ---------------------------------------------------------
        start = time.perf_counter()
        with suppress_stdout():
            sym_cnt, _, _, S_reach, bdd_mgr = run_symbolic_search(net)
        sym_time = (time.perf_counter() - start) * 1000

        # ---------------------------------------------------------
        # TASK 4A: CEGAR (Code cũ)
        # ---------------------------------------------------------
        cegar_time = -1
        cegar_example = "N/A"

        if check_deadlock_cegar:
            try:
                start_c = time.perf_counter()
                with suppress_stdout():
                    has_deadlock_cegar, cegar_example = check_deadlock_cegar(net, S_reach, bdd_mgr)
                cegar_time = (time.perf_counter() - start_c) * 1000
            except Exception:
                cegar_time = -1
                cegar_example = "N/A"

        # ---------------------------------------------------------
        # TASK 4B: SYMBOLIC INTERSECTION (Code mới)
        # ---------------------------------------------------------
        start_sym = time.perf_counter()
        place_order, _ = build_place_index(net)
        x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]

        dead_condition = build_dead_formula(bdd_mgr, net, place_order, x_ids)
        deadlock_set = bdd_mgr.land(S_reach, dead_condition)

        has_deadlock = (deadlock_set != bdd_mgr.bdd.false)
        sym_example = "N/A"

        if has_deadlock:
            dead_vec = extract_marking_from_bdd(bdd_mgr, deadlock_set, place_order)
            sym_example = format_marking(dead_vec, place_order, net)

        my_time = (time.perf_counter() - start_sym) * 1000

        # Tính Speedup
        speedup = 0
        if cegar_time > 0 and my_time > 0:
            speedup = cegar_time / my_time

        print(f"{' ' * 80}", end="\r")

        return {
            "Model": filename,
            "# Places": num_places,
            "Reachable States": sym_cnt,
            "BFS Time": bfs_time,
            "DFS Time": dfs_time,
            "Sym Time": sym_time,

            # Deadlock Data
            "Deadlock?": "YES" if has_deadlock else "NO",
            "T_CEGAR": cegar_time,
            "T_Symbolic": my_time,
            "Speedup": speedup,
            "Ex_Symbolic": sym_example,
            "Ex_CEGAR": cegar_example,
        }

    except Exception as e:
        print(f"\n{Color.RED}Error: {e}{Color.RESET}")
        return None


# =============================================================
# PRINTING FUNCTIONS
# =============================================================

def print_table_1(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 1: Reachability Analysis (Explicit vs Symbolic){Color.RESET}")
    columns = [
        ("Model", 30, "Model"),
        ("#P", 4, "# Places"),
        ("#Reachable", 12, "Reachable States"),
        ("BFS [ms]", 12, "BFS Time"),
        ("DFS [ms]", 12, "DFS Time"),
        ("BDD [ms]", 12, "Sym Time"),
    ]
    _print_generic_table(data, columns)


def print_table_2(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 2: Symbolic Deadlock Detection Results (Optimized Method){Color.RESET}")
    columns = [
        ("Model", 30, "Model"),
        ("Deadlock?", 10, "Deadlock?"),
        ("Time [ms]", 12, "T_Symbolic"),
        ("Example deadlock marking", 60, "Ex_Symbolic"),
    ]
    _print_generic_table(data, columns)


def print_table_3_comparison(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 3: Performance Comparison (CEGAR vs Symbolic Intersection){Color.RESET}")
    print(f"{Color.GRAY}(T.Symbolic is your optimized method. Speedup = T.CEGAR / T.Symbolic){Color.RESET}")

    columns = [
        ("Model", 30, "Model"),
        ("T. CEGAR [ms]", 15, "T_CEGAR"),
        ("T. Symbolic [ms]", 16, "T_Symbolic"),
        ("Speedup", 10, "Speedup"),
        ("Result", 8, "Deadlock?"),
        ("Example (Symbolic)", 35, "Ex_Symbolic"),
        ("Example (CEGAR)", 35, "Ex_CEGAR"),
    ]

    header = ""
    sep = ""
    for title, w, _ in columns:
        header += f"{title:<{w}} | "
        sep += "-" * (w + 1) + "+"
    print("-" * len(sep))
    print(header)
    print(sep)

    for row in data:
        line = ""
        for _, w, key in columns:
            val = row.get(key, "")

            if key == "Speedup":
                sp = float(val)
                cell = f"{sp:.1f}x"
                if sp > 10:
                    cell = f"{Color.GREEN}{cell:<{w}}{Color.RESET}"
                elif sp < 1:
                    cell = f"{Color.RED}{cell:<{w}}{Color.RESET}"
                else:
                    cell = f"{cell:<{w}}"

            elif "T_" in key:  # Time columns
                if val == -1:
                    cell = f"{Color.RED}{'N/A':<{w}}{Color.RESET}"
                else:
                    cell = f"{float(val):<{w}.4f}"

            elif key == "Deadlock?":
                c = Color.RED if val == "YES" else Color.GREEN
                cell = f"{c}{val:<{w}}{Color.RESET}"

            elif "Ex_" in key:  # Example columns
                text = str(val)
                # Cắt bớt nếu dài quá
                if len(text) > w:
                    text = text[:w - 3] + "..."
                if text == "N/A":
                    cell = f"{Color.GRAY}{text:<{w}}{Color.RESET}"
                else:
                    cell = f"{Color.YELLOW}{text:<{w}}{Color.RESET}"
            else:
                cell = f"{str(val):<{w}}"

            line += cell + " | "
        print(line)
    print("-" * len(sep))


def _print_generic_table(data, columns):
    header = ""
    sep = ""
    for title, w, _ in columns:
        header += f"{title:<{w}} | "
        sep += "-" * (w + 1) + "+"
    print("-" * len(sep))
    print(header)
    print(sep)
    for row in data:
        line = ""
        for _, w, key in columns:
            val = row.get(key, "")
            if key == "Reachable States":
                v = int(val)
                val_str = f"{v:,}" if len(str(v)) <= w else f"{v:.1e}"
                cell = f"{val_str:<{w}}"
            elif "Time" in key:
                cell = f"{float(val):<{w}.4f}"
            elif key == "Deadlock?":
                c = Color.RED if val == "YES" else Color.GREEN
                cell = f"{c}{val:<{w}}{Color.RESET}"
            elif "Ex_" in key:
                cell = f"{Color.YELLOW}{str(val):<{w}}{Color.RESET}"
            else:
                cell = f"{str(val):<{w}}"
            line += cell + " | "
        print(line)
    print("-" * len(sep))


# =============================================================
# MAIN
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Standard PNMLs")
    parser.add_argument("--dir", type=str, default=default_dir)
    args = parser.parse_args()

    if os.path.isdir(args.dir):
        files = glob.glob(os.path.join(args.dir, "*.pnml"))
    else:
        files = glob.glob(args.dir)
    if not files:
        files = glob.glob("*.pnml")

    if not files:
        print(f"{Color.YELLOW}⚠️ No .pnml files found.{Color.RESET}")
        sys.exit(0)

    files.sort()
    print(f"{Color.BOLD}🚀 Starting Benchmark on {len(files)} files...{Color.RESET}")

    results = []
    for f in files:
        res = run_benchmark_on_file(f)
        if res:
            results.append(res)

    # In 3 bảng
    print_table_1(results)
    print("\n" + " " * 30 + "---" * 5 + "\n")
    print_table_2(results)
    print("\n" + " " * 30 + "---" * 5 + "\n")
    print_table_3_comparison(results)

    print(f"\nGenerated at: {time.strftime('%H:%M:%S')}")
