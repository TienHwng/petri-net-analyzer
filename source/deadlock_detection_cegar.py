# =============================================================
# deadlock_detection_cegar.py
# Task 4: CEGAR Deadlock Detection (State Eq Abstraction + BDD Refinement)
# Fixed: Windows Encoding Errors & Missing Attributes for Benchmark
# =============================================================

import os
import sys
import time
import argparse
import collections
from typing import List, Dict, Set, Tuple

# Tăng giới hạn đệ quy
sys.setrecursionlimit(50000)


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# --- IMPORTS TỪ CÁC MODULE KHÁC ---
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

    from parser import parse_pnml, PetriNet
    from reachability import build_place_index, pretty_marking_vec, auto_group_places

    # Import từ file symbolic.py (chứa code dùng thư viện dd)
    from symbolic_computation_BDD import run_symbolic_search
except ImportError as e:
    # [FIX] Removed Emoji
    print(f"{Color.RED}[X] Import Error: {e}{Color.RESET}")
    print("Please ensure parser.py, reachability.py, and symbolic_computation_BDD.py are available.")
    sys.exit(1)

# Import thư viện PuLP
try:
    import pulp

    HAS_PULP = True
except ImportError:
    HAS_PULP = False
    # [FIX] Removed Emoji
    print(f"{Color.YELLOW}[!] Warning: 'pulp' library not found. ILP check skipped.{Color.RESET}")


# =============================================================
# 1. ILP ABSTRACTION BUILDER (State Equation + Structural Deadlock)
# =============================================================

def build_cegar_ilp(net, place_order):
    """
    Xây dựng mô hình ILP trừu tượng ban đầu:
    Minimize Sigma (Parikh vector)
    Subject to:
      1. Deadlock Structure: Disable all transitions
      2. State Equation: M = M0 + C * Sigma
    """
    prob = pulp.LpProblem("CEGAR_Deadlock", pulp.LpMinimize)

    # Biến: M (Marking, giả sử 1-safe) và Sigma (Số lần bắn transition)
    m_vars = {p: pulp.LpVariable(f"m_{p}", cat=pulp.LpBinary) for p in place_order}
    t_ids = list(net.transitions.keys())
    sigma_vars = {t: pulp.LpVariable(f"sigma_{t}", lowBound=0, cat=pulp.LpInteger) for t in t_ids}

    # Hàm mục tiêu: Tìm đường đi ngắn nhất (heuristic)
    prob += pulp.lpSum(sigma_vars.values())

    # Ràng buộc 1: Structural Deadlock (Mọi transition đều bị disable)
    # Disabled(t) := Sum(tokens in input places) <= |input places| - 1
    for t_id in t_ids:
        inputs = [p for (p, w) in net.input_arcs.get(t_id, [])]
        if inputs:
            # Chỉ xét các input places có trong place_order
            valid_inputs = [p for p in inputs if p in m_vars]
            if valid_inputs:
                prob += pulp.lpSum([m_vars[p] for p in valid_inputs]) <= len(valid_inputs) - 1

    # Ràng buộc 2: State Equation (M = M0 + C * Sigma)
    for p in place_order:
        m0_val = 1 if net.places[p].initial_marking > 0 else 0

        # Tính delta = Flow_In - Flow_Out
        delta_expr = 0
        for t in t_ids:
            weight_out = 0  # t -> p
            weight_in = 0  # p -> t

            for (pid, w) in net.output_arcs.get(t, []):
                if pid == p:
                    weight_out += w
            for (pid, w) in net.input_arcs.get(t, []):
                if pid == p:
                    weight_in += w

            diff = weight_out - weight_in
            if diff != 0:
                delta_expr += diff * sigma_vars[t]

        prob += (m_vars[p] == m0_val + delta_expr, f"StateEq_{p}")

    return prob, m_vars, sigma_vars


# =============================================================
# 2. CEGAR LOOP LOGIC
# =============================================================

def check_deadlock_cegar(net, reach_node, bdd_mgr) -> Tuple[bool, str]:
    """
    Chạy vòng lặp CEGAR để kiểm tra deadlock.
    Trả về:
        has_deadlock: True nếu tìm được deadlock thực.
        example_str : chuỗi liệt kê các place có token (marking = 1),
                      dùng cho cột "Example (CEGAR)" trong benchmark.
    Ghi chú:
        - Khi chạy trực tiếp script, ta vẫn in ra dạng đầy đủ nhóm (pretty_marking_vec).
        - Khi dùng cho benchmark, chỉ cần chuỗi rút gọn (các place có 1 token).
    """
    print(f"\n{Color.BOLD}STEP 2: DEADLOCK DETECTION (CEGAR Loop){Color.RESET}")
    start_time = time.perf_counter()

    place_order, _ = build_place_index(net)

    # Hàm phụ: rút gọn marking chỉ giữ các place có token = 1
    def _compact_marking(dead_marking_vec):
        active = []
        for i, val in enumerate(dead_marking_vec):
            if val > 0:
                p_id = place_order[i]
                p_obj = net.places.get(p_id)
                name = getattr(p_obj, "name", None) or p_id
                active.append(str(name))
        return ", ".join(active) if active else "Empty"

    # Mapping tên biến BDD ("x_ID") để verify
    curr_vars_map = {p: f"x_{p}" for p in place_order}

    # --- Initial Abstraction ---
    print("   [CEGAR] Building Initial Abstraction (State Equation)...")
    prob, m_vars, sigma_vars = build_cegar_ilp(net, place_order)

    iteration = 0
    while True:
        iteration += 1
        print(f"   [CEGAR] Iteration {iteration}: Solving ILP...")

        # 1. Solve Abstraction
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        # Nếu ILP vô nghiệm -> Hệ thống an toàn
        if status != pulp.LpStatusOptimal:
            print(f"\n{Color.GREEN}[OK] CONCLUSION: NO DEADLOCK FOUND.{Color.RESET}")
            print("   The system is structurally deadlock-free (Verified by State Equation).")
            print(f"   Total iterations: {iteration}")
            print(f"   Total time: {time.perf_counter() - start_time:.4f}s")
            return False, "N/A"

        # 2. Extract Candidate Marking
        candidate_m: Dict[str, int] = {}
        for p in place_order:
            val = pulp.value(m_vars[p])
            candidate_m[p] = 0 if val is None else int(round(val))

        # 3. Verify with BDD (Is this candidate Reachable?)
        cube_node = bdd_mgr.bdd.true
        for p in place_order:
            var_name = curr_vars_map[p]
            try:
                var_node = bdd_mgr.var(var_name)
            except KeyError:
                # Place không có trong BDD (không dùng trong symbolic), bỏ qua
                continue

            if candidate_m[p] == 1:
                cube_node = bdd_mgr.land(cube_node, var_node)
            else:
                cube_node = bdd_mgr.land(cube_node, bdd_mgr.lnot(var_node))

        # Intersection: Reachable AND Candidate
        intersection = bdd_mgr.land(reach_node, cube_node)

        if intersection != bdd_mgr.bdd.false:
            # --- REAL DEADLOCK FOUND ---
            print(f"\n{Color.RED}[X] CONCLUSION: DEADLOCK DETECTED!{Color.RESET}")
            print(f"   Iteration: {iteration}")

            # Format output: console dùng bản đầy đủ, benchmark dùng bản rút gọn
            dead_marking_vec = [candidate_m[p] for p in place_order]
            groups = auto_group_places(net)
            console_str = pretty_marking_vec(dead_marking_vec, net, place_order, groups)
            example_str = _compact_marking(dead_marking_vec)

            print("\n   [Example Deadlock Marking]:")
            print(console_str)

            # In Parikh Vector (Trace Summary từ ILP)
            print(f"\n{Color.CYAN}--- [ILP] State Equation Verification (Result from CEGAR) ---{Color.RESET}")
            print(f"{Color.GREEN}[OK] State Equation Satisfied!{Color.RESET}")
            fired = []
            for t in net.transitions:
                val = pulp.value(sigma_vars[t])
                if val and val > 0:
                    t_name = t
                    if hasattr(net, "transition_id_to_name") and net.transition_id_to_name:
                        t_name = net.transition_id_to_name.get(t, t)
                    elif hasattr(net.transitions[t], "name") and net.transitions[t].name:
                        t_name = net.transitions[t].name
                    fired.append(f"{t_name}: {int(val)}")
            print(f"   Parikh Vector: [{', '.join(fired)}]")

            # Trace Reconstruction (BFS)
            find_trace_to_deadlock(net, place_order, dead_marking_vec)

            print(f"   -> Detection Time: {time.perf_counter() - start_time:.6f}s")
            return True, example_str
        else:
            # --- SPURIOUS COUNTER-EXAMPLE (Refinement) ---
            print("   -> Spurious Deadlock found (Math valid, but Unreachable). Refining...")

            # Thêm Canonical Cut để loại bỏ candidate này khỏi ILP
            # Sum(vars=1) - Sum(vars=0) <= Count(vars=1) - 1
            vars_1 = [m_vars[p] for p in place_order if candidate_m[p] == 1]
            vars_0 = [m_vars[p] for p in place_order if candidate_m[p] == 0]

            if len(vars_1) > 0:
                prob += (pulp.lpSum(vars_1) - pulp.lpSum(vars_0)) <= len(vars_1) - 1
            else:
                prob += pulp.lpSum(m_vars.values()) >= 1

    # Fallback (không nên tới đây, để type cho chắc)
    return False, "N/A"


def find_trace_to_deadlock(net: PetriNet, place_order: List[str], target_marking: List[int]):
    print(f"\n{Color.CYAN}--- [Trace] Reconstructing Firing Sequence (BFS) ---{Color.RESET}")
    start_time = time.perf_counter()

    target_tuple = tuple(target_marking)
    m0_list = [1 if net.places[p].initial_marking > 0 else 0 for p in place_order]
    m0_tuple = tuple(m0_list)

    if m0_tuple == target_tuple:
        print("   -> Initial marking is already the deadlock.")
        return

    queue = collections.deque([(m0_tuple, [])])
    visited = {m0_tuple}

    trans_data = []
    for t_id in net.transitions:
        pre_idxs = [place_order.index(pid) for pid, w in net.input_arcs.get(t_id, []) if pid in place_order]
        post_idxs = [place_order.index(pid) for pid, w in net.output_arcs.get(t_id, []) if pid in place_order]
        trans_data.append((t_id, pre_idxs, post_idxs))

    MAX_STATES = 200000
    steps = 0

    while queue:
        curr_m, path = queue.popleft()
        steps += 1
        if steps > MAX_STATES:
            print(f"   (Trace search stopped after {MAX_STATES} states - too deep/complex)")
            return

        for t_id, pre_idxs, post_idxs in trans_data:
            if all(curr_m[idx] == 1 for idx in pre_idxs):
                new_m_list = list(curr_m)
                for idx in pre_idxs:
                    new_m_list[idx] = 0
                for idx in post_idxs:
                    new_m_list[idx] = 1
                new_m = tuple(new_m_list)

                if new_m == target_tuple:
                    final_path = path + [t_id]
                    # [FIX] An toàn khi lấy tên transition cho Trace
                    t_names = []
                    for t in final_path:
                        name = t
                        if hasattr(net, "transition_id_to_name") and net.transition_id_to_name:
                            name = net.transition_id_to_name.get(t, t)
                        elif hasattr(net.transitions[t], "name") and net.transitions[t].name:
                            name = net.transitions[t].name
                        t_names.append(name)

                    print(f"   -> Path Found ({len(final_path)} steps):")
                    print(f"      {' -> '.join(t_names)}")
                    print(f"   -> Time: {time.perf_counter() - start_time:.4f}s")
                    return

                if new_m not in visited:
                    visited.add(new_m)
                    queue.append((new_m, path + [t_id]))

    print("   -> Trace not found (BFS exhaust).")


# =============================================================
# MAIN EXECUTION
# =============================================================

def solve_task4_complete(pnml_path: str):
    # [FIX] Removed Emoji
    print(f"[FILE] Model: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net:
        return
    net.transition_id_to_name = {t_id: t_obj.name for t_id, t_obj in net.transitions.items()}

    # --- STEP 1: SYMBOLIC REACHABILITY (Oracle) ---
    print(f"\n{Color.BOLD}STEP 1: REACHABILITY (using 'dd' library){Color.RESET}")
    print("   (Calculating Exact Reachability to serve as CEGAR Oracle...)")

    # run_symbolic_search trả về (count, time, mem, REACHED_NODE, MANAGER_ADAPTER)
    count, t_reach, mem, S_reach, bdd_mgr = run_symbolic_search(net)

    print(f"   -> Reachable States: {count}")
    print(f"   -> Time: {t_reach:.4f}s")

    # --- STEP 2: CEGAR DEADLOCK DETECTION ---
    if not HAS_PULP:
        # [FIX] Removed Emoji
        print(f"{Color.RED}[X] Cannot run CEGAR without PuLP library.{Color.RESET}")
        return

    check_deadlock_cegar(net, S_reach, bdd_mgr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 4 Complete: Deadlock Detection (CEGAR)")
    parser.add_argument("--model", type=str, default="file1_cabines_1safe.pnml")
    args = parser.parse_args()

    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)
        if not os.path.exists(pnml_path):
            pnml_path = os.path.join(base_dir, "../Standard PNMLs", args.model)

    if not os.path.exists(pnml_path):
        print(f"File not found: {args.model}")
        sys.exit(1)

    solve_task4_complete(pnml_path)