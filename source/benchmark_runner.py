import os
import sys
import time
import glob
import argparse
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


# --- Import các module của bạn ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from parser import parse_pnml
    from reachability import build_place_index
    # Import Task 3 và hàm Explicit Search
    from symbolic_computation_BDD import run_symbolic_search, run_explicit_search
    # Import Task 4 logic
    from deadlock_detection import build_dead_formula, extract_marking_from_bdd
except ImportError as e:
    print(f"{Color.RED}❌ Lỗi Import: {e}{Color.RESET}")
    print("Hãy đảm bảo các file parser.py, symbolic_computation_BDD.py, task4_deadlock_complete.py nằm cùng thư mục.")
    sys.exit(1)


# =============================================================
# UTILS: FORMATTING DEADLOCK STRING
# =============================================================
def format_deadlock_example(marking_vec: List[int], place_order: List[str], net) -> str:
    """
    Chuyển vector deadlock thành chuỗi tên place.
    Không cắt bớt chuỗi (No truncation).
    """
    if not marking_vec:
        return "N/A"

    active_places = []
    for i, val in enumerate(marking_vec):
        if val > 0:
            p_id = place_order[i]
            # Lấy object place từ net để lấy tên (name)
            p_obj = net.places.get(p_id)

            # Ưu tiên lấy Name, nếu không có thì lấy ID
            if p_obj and hasattr(p_obj, 'name') and p_obj.name:
                active_places.append(str(p_obj.name))
            else:
                active_places.append(str(p_id))

    if not active_places:
        return "Empty Marking"

    # Join toàn bộ, không cắt bớt
    full_str = ", ".join(active_places)
    return full_str


# =============================================================
# BENCHMARK ENGINE
# =============================================================

def run_benchmark_on_file(filepath: str):
    filename = os.path.basename(filepath)
    print(f"Processing: {Color.CYAN}{filename:<30}{Color.RESET}", end="\r")

    try:
        # 1. Parse PNML
        net = parse_pnml(filepath)
        if not net: return None
        num_places = len(net.places)

        # 2. Explicit Reachability (BFS & DFS) - Task 2
        # Đo riêng BFS
        bfs_cnt, bfs_time, bfs_mem_bytes, _ = run_explicit_search(net, 'BFS')
        # Đo riêng DFS
        dfs_cnt, dfs_time, dfs_mem_bytes, _ = run_explicit_search(net, 'DFS')

        # 3. Symbolic Reachability - Task 3
        sym_cnt, sym_time, sym_mem_bytes, S_reach, bdd_mgr = run_symbolic_search(net)

        # 4. Deadlock Detection - Task 4
        start_t4 = time.perf_counter()
        place_order, _ = build_place_index(net)
        x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]

        dead_condition = build_dead_formula(bdd_mgr, net, place_order, x_ids)
        deadlock_set = bdd_mgr.land(S_reach, dead_condition)

        has_deadlock = (deadlock_set != bdd_mgr.bdd.false)
        example_str = "N/A"
        if has_deadlock:
            dead_vec = extract_marking_from_bdd(bdd_mgr, deadlock_set, place_order)
            example_str = format_deadlock_example(dead_vec, place_order, net)

        end_t4 = time.perf_counter()
        time_t4 = end_t4 - start_t4

        print(f"{' ' * 80}", end="\r")  # Clear line

        # Return dict with Time in ms
        return {
            "Model": filename,
            "# Places": num_places,
            "Reachable States": sym_cnt,
            "BFS Time": bfs_time * 1000,
            "DFS Time": dfs_time * 1000,
            "Sym Time": sym_time * 1000,
            "Deadlock?": "YES" if has_deadlock else "NO",
            "Task 4 Time": time_t4 * 1000,
            "Example": example_str
        }

    except Exception as e:
        print(f"\n{Color.RED}Error processing {filename}: {e}{Color.RESET}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================
# PRINTING FUNCTIONS
# =============================================================

def print_table_1_reachability(data: List[Dict]):
    """Table 1: Comparison Explicit vs Symbolic"""
    print(f"\n{Color.BOLD}Table 1: Comparison between explicit (BFS/DFS) and symbolic reachability{Color.RESET}")

    # [UPDATE] Tăng độ rộng cột để chứa 6 số thập phân
    columns = [
        ("Model", 30, "Model"),
        ("#P", 4, "# Places"),
        ("#Reachable", 12, "Reachable States"),
        ("Time BFS [ms]", 15, "BFS Time"),
        ("Time DFS [ms]", 15, "DFS Time"),
        ("Time BDD [ms]", 15, "Sym Time")
    ]

    # Print Header
    header = ""
    sep = ""
    for title, w, _ in columns:
        header += f"{title:<{w}} | "
        sep += "-" * (w + 1) + "+"

    print("-" * len(sep))
    print(header)
    print(sep)

    # Print Rows
    for row in data:
        line = ""
        for _, w, key in columns:
            val = row.get(key, "")

            if key == "Reachable States":
                val_fmt = f"{int(val):,}"
                if len(val_fmt) > w: val_fmt = f"{int(val):.1e}"
                cell = f"{val_fmt:<{w}}"
            elif "Time" in key:
                # [UPDATE] 6 số sau dấu phẩy (.6f)
                cell = f"{float(val):<{w}.6f}"
            else:
                cell = f"{str(val):<{w}}"

            line += cell + " | "
        print(line)
    print("-" * len(sep))


def print_table_2_deadlock(data: List[Dict]):
    """Table 2: Deadlock Detection"""
    print(f"\n{Color.BOLD}Table 2: Symbolic Deadlock Detection with ILP Verification{Color.RESET}")

    # [UPDATE] Tăng độ rộng cột thời gian
    columns = [
        ("Model", 30, "Model"),
        ("Deadlock?", 10, "Deadlock?"),
        ("Time [ms]", 15, "Task 4 Time"),
        ("Example deadlock marking", 80, "Example")
    ]

    # Print Header
    header = ""
    sep = ""
    for title, w, _ in columns:
        header += f"{title:<{w}} | "
        sep += "-" * (w + 1) + "+"

    print("-" * len(sep))
    print(header)
    print(sep)

    # Print Rows
    for row in data:
        line = ""
        for _, w, key in columns:
            val = row.get(key, "")

            if key == "Deadlock?":
                text = str(val)
                color = Color.RED if text == "YES" else Color.GREEN
                padding = w - len(text)
                cell = f"{color}{text}{Color.RESET}{' ' * padding}"
            elif key == "Task 4 Time":
                # [UPDATE] 6 số sau dấu phẩy (.6f)
                cell = f"{float(val):<{w}.6f}"
            elif key == "Example":
                text = str(val)
                if text == "N/A":
                    cell = f"{Color.GRAY}{text:<{w}}{Color.RESET}"
                else:
                    cell = f"{Color.YELLOW}{text:<{w}}{Color.RESET}"
            else:
                cell = f"{str(val):<{w}}"

            line += cell + " | "
        print(line)
    print("-" * len(sep))


# =============================================================
# MAIN
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Runner")
    default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Standard PNMLs")
    parser.add_argument("--dir", type=str, default=default_dir, help="Directory containing .pnml files")
    args = parser.parse_args()

    if os.path.isdir(args.dir):
        files = glob.glob(os.path.join(args.dir, "*.pnml"))
    else:
        files = glob.glob(args.dir)

    if not files: files = glob.glob("*.pnml")
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

    # IN 2 BẢNG RIÊNG BIỆT
    print_table_1_reachability(results)
    print("\n" + " " * 20 + "---" * 10 + "\n")
    print_table_2_deadlock(results)

    print(f"\nGenerated at: {time.strftime('%H:%M:%S')}")