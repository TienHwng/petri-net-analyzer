# =============================================================
# task4_deadlock_complete.py
# Task 4: Complete Deadlock Detection (Final Optimized Version)
# Features: Symbolic Detection, ILP Verification, Trace Reconstruction.
# =============================================================

import os
import sys
import time
import argparse
import collections
from typing import List, Dict, Set, Tuple

# Tăng giới hạn đệ quy cho BDD
sys.setrecursionlimit(50000)


# --- CLASS MÀU SẮC (FIX LỖI NAME ERROR) ---
class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# --- IMPORTS TỪ CÁC MODULE KHÁC ---
try:
    # Tự động thêm đường dẫn hiện tại vào sys.path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

    # Giả định các file cơ bản (parser, reachability, symbolic_computation_BDD) đã có
    from parser import parse_pnml, PetriNet
    from reachability import build_place_index, pretty_marking_vec, auto_group_places
    from symbolic_computation_BDD import run_symbolic_search_pure, BDD
except ImportError as e:
    print(f"{Color.RED}❌ Import Error: {e}{Color.RESET}")
    print("Please ensure parser.py, reachability.py, and symbolic_computation_BDD.py are available.")
    sys.exit(1)

# Import thư viện PuLP cho phần ILP
try:
    import pulp

    HAS_PULP = True
except ImportError:
    HAS_PULP = False
    print(f"{Color.YELLOW}⚠️ Warning: 'pulp' library not found. ILP State Equation check will be skipped.{Color.RESET}")


# =============================================================
# 1. BDD LOGIC: DEADLOCK FORMULATION
# =============================================================

def build_dead_formula(bdd: BDD, net: PetriNet, place_order: List[str], x_ids: List[int]) -> int:
    """
    Xây dựng công thức BDD đại diện cho tập các trạng thái chết.
    Dead = AND ( NOT (Enabled(t)) ) với mọi t.
    """
    pid_to_idx = {pid: i for i, pid in enumerate(place_order)}
    Any_Enabled = 0  # False

    for t_id in net.transitions:
        pre = {pid for pid, w in net.input_arcs.get(t_id, [])}
        post = {pid for pid, w in net.output_arcs.get(t_id, [])}

        # Điều kiện Enable: Pre có token (=1) VÀ (Post-Pre) không có token (=0) (với 1-safe)
        En_t = 1

        for pid in pre:
            idx = pid_to_idx[pid]
            En_t = bdd.land(En_t, x_ids[idx])

        for pid in (post - pre):
            idx = pid_to_idx[pid]
            En_t = bdd.land(En_t, bdd.lnot(x_ids[idx]))

        Any_Enabled = bdd.lor(Any_Enabled, En_t)

    return bdd.lnot(Any_Enabled)


def extract_marking_from_bdd(bdd: BDD, node: int, var_order: List[str]) -> List[int]:
    """Trích xuất 1 nghiệm (marking vector) từ node BDD."""
    if node == 0: return None
    assignment = {}

    # DFS tìm đường đi đến node 1 (True)
    def dfs(u):
        if u == 1: return True
        if u == 0: return False

        lvl, low, high = bdd.nodes[u]
        var_name = bdd.level2var[lvl]

        # Ưu tiên nhánh 1 để tìm marking có token
        if dfs(high):
            assignment[var_name] = 1
            return True
        if dfs(low):
            assignment[var_name] = 0
            return True
        return False

    dfs(node)

    # Map về vector theo thứ tự biến x_
    marking = []
    x_vars = [v for v in var_order if v.startswith("x_")]
    for v in x_vars:
        marking.append(assignment.get(v, 0))
    return marking


# =============================================================
# 2. ILP CHECK: STATE EQUATION (M = M0 + C*sigma)
# =============================================================

def verify_with_ilp(net: PetriNet, place_order: List[str], target_marking: List[int]):
    """
    Sử dụng PuLP để kiểm tra phương trình trạng thái (State Equation).
    Tìm sigma >= 0 sao cho: C * sigma = M_dead - M_0
    """
    if not HAS_PULP: return

    print(f"\n{Color.CYAN}--- [ILP] State Equation Verification (using PuLP) ---{Color.RESET}")

    # Tạo bài toán
    prob = pulp.LpProblem("StateEquationCheck", pulp.LpMinimize)

    # Biến: sigma (số lần bắn của mỗi transition), nguyên không âm
    t_ids = list(net.transitions.keys())
    sigma_vars = {t: pulp.LpVariable(f"sigma_{t}", lowBound=0, cat=pulp.LpInteger) for t in t_ids}

    # Hàm mục tiêu giả
    prob += pulp.lpSum(sigma_vars.values())

    # Lấy M0 gốc từ file PNML
    raw_m0 = [net.places[p].initial_marking for p in place_order]

    # "Ép" M0 về dạng 1-safe (nếu > 0 thì bằng 1) để khớp với giả định của BDD
    m0_safe = [1 if m > 0 else 0 for m in raw_m0]

    # Ràng buộc: M_dead = M0_safe + C * sigma => C * sigma = M_dead - M0_safe
    for i, p_id in enumerate(place_order):
        delta_p = target_marking[i] - m0_safe[i]

        # Tính dòng của ma trận C tương ứng với p
        constraint_expr = 0
        for t in t_ids:
            weight = 0
            # Output arcs (t -> p)
            for (pid, w) in net.output_arcs.get(t, []):
                if pid == p_id: weight += w
            # Input arcs (p -> t)
            for (pid, w) in net.input_arcs.get(t, []):
                if pid == p_id: weight -= w

            if weight != 0:
                constraint_expr += weight * sigma_vars[t]

        prob += (constraint_expr == delta_p, f"Flow_Constraint_{p_id}")

    # Giải
    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if status == pulp.LpStatusOptimal:
        print(f"{Color.GREEN}✅ State Equation Satisfied! (1-Safe Consistent){Color.RESET}")
        print(f"   Firing Vector (Parikh vector):")
        fired = []
        for t in t_ids:
            val = pulp.value(sigma_vars[t])
            if val and val > 0:
                t_name = net.transition_id_to_name.get(t, t)  # <-- GET NAME HERE
                fired.append(f"{t_name}: {int(val)}")
        print(f"   Trace Summary: [{', '.join(fired)}]")
    else:
        print(f"{Color.RED}❌ State Equation Violated!{Color.RESET}")
        print("   -> Deadlock might be reachable but structurally invisible to State Eq.")


# =============================================================
# 3. TRACE: RECONSTRUCT PATH (BFS)
# =============================================================

def find_trace_to_deadlock(net: PetriNet, place_order: List[str], target_marking: List[int]):
    """
    Tìm đường đi ngắn nhất từ M0 đến M_dead bằng BFS tường minh.
    (Chỉ khả thi khi không gian trạng thái không quá bùng nổ)
    """
    if not HAS_PULP: return  # Chỉ chạy nếu PuLP có sẵn (Vì nó là phần bổ sung)

    print(f"\n{Color.CYAN}--- [Trace] Reconstructing Firing Sequence ---{Color.RESET}")
    start_time = time.perf_counter()

    target_tuple = tuple(target_marking)
    m0_list = [net.places[p].initial_marking for p in place_order]
    m0_tuple = tuple(m0_list)

    if m0_tuple == target_tuple:
        print("   -> Initial marking is already the deadlock.")
        return

    # BFS Queue: (current_marking_tuple, path_of_transitions)
    queue = collections.deque([(m0_tuple, [])])
    visited = {m0_tuple}

    # Cache cấu trúc mạng để chạy nhanh hơn (Pre-process)
    trans_data = []
    for t_id in net.transitions:
        # Pre indices (chỉ số của input places)
        pre_idxs = []
        for pid, w in net.input_arcs.get(t_id, []):
            if pid in place_order: pre_idxs.append(place_order.index(pid))

        # Post indices (chỉ số của output places)
        post_idxs = []
        for pid, w in net.output_arcs.get(t_id, []):
            if pid in place_order: post_idxs.append(place_order.index(pid))

        trans_data.append((t_id, pre_idxs, post_idxs))

    # Limit search space to avoid hang on huge nets
    MAX_STATES = 100000

    steps = 0
    while queue:
        curr_m, path = queue.popleft()
        steps += 1

        if steps > MAX_STATES:
            print(f"   (Trace search stopped after {MAX_STATES} states visited - too deep)")
            return

        # Check enabled transitions using cached data
        for t_id, pre_idxs, post_idxs in trans_data:
            # Check enabled
            enabled = True
            for idx in pre_idxs:
                if curr_m[idx] < 1:  # Assuming weight 1 for simplicity
                    enabled = False
                    break

            if enabled:
                # Fire transition (Tính marking mới)
                new_m_list = list(curr_m)

                # 1. Trừ token (1-safe: gán về 0)
                for idx in pre_idxs:
                    new_m_list[idx] = 0

                    # 2. Cộng token (1-safe: gán lên 1)
                for idx in post_idxs:
                    new_m_list[idx] = 1

                new_m = tuple(new_m_list)

                if new_m == target_tuple:
                    final_path_ids = path + [t_id]

                    # --- CHUYỂN ID SANG TÊN ---
                    t_names = [net.transition_id_to_name.get(t, t) for t in final_path_ids]

                    print(f"   -> Path Found (Length {len(final_path_ids)}):")
                    print(f"      {' -> '.join(t_names)}")  # <-- PRINT NAMES
                    print(f"   -> Trace Time: {time.perf_counter() - start_time:.4f}s")
                    return

                if new_m not in visited:
                    visited.add(new_m)
                    queue.append((new_m, path + [t_id]))

    print("   -> Trace not found (Deadlock might be unreachable in explicit graph or graph too large).")


# =============================================================
# MAIN EXECUTION
# =============================================================

def solve_task4_complete(pnml_path: str):
    print(f"📂 Model: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net: return
    net.transition_id_to_name = {t_id: t_obj.name for t_id, t_obj in net.transitions.items()}
    # --- STEP 1: SYMBOLIC REACHABILITY (TASK 3) ---
    print(f"\n{Color.BOLD}STEP 1: COMPUTING REACHABILITY (BDD - Task 3){Color.RESET}")

    count, t_reach, mem, S_reach, bdd_mgr = run_symbolic_search_pure(net)
    print(f"   -> Reachable States: {count}")
    print(f"   -> BDD Construction Time: {t_reach:.4f}s")

    # Chuẩn bị dữ liệu
    place_order, _ = build_place_index(net)
    x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]
    var_order = [bdd_mgr.level2var[i] for i in range(len(bdd_mgr.var2level))]

    # --- STEP 2: DEADLOCK DETECTION (LOGIC) ---
    print(f"\n{Color.BOLD}STEP 2: DEADLOCK DETECTION (Intersection){Color.RESET}")

    start_detect = time.perf_counter()

    # 2a. Build Dead Formula
    Dead_Condition = build_dead_formula(bdd_mgr, net, place_order, x_ids)

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
        dead_marking = extract_marking_from_bdd(bdd_mgr, Deadlock_Set, var_order)
        groups = auto_group_places(net)

        print("\n   [Example Deadlock Marking]:")
        print(pretty_marking_vec(dead_marking, net, place_order, groups))

        # --- STEP 3: ILP VERIFICATION ---
        verify_with_ilp(net, place_order, dead_marking)

        # --- STEP 4: TRACE RECONSTRUCTION ---
        find_trace_to_deadlock(net, place_order, dead_marking)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 4 Complete: Deadlock Detection")
    parser.add_argument("--model", type=str, default="philo.pnml")
    args = parser.parse_args()

    # --- LOGIC XỬ LÝ PATH THÔNG MINH ---
    pnml_path = os.path.normpath(args.model)

    # 1. Kiểm tra đường dẫn trực tiếp (CWD)
    if not os.path.exists(pnml_path):
        # 2. Kiểm tra đường dẫn tương đối so với file script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

        # 3. (Optional) Nếu không tìm thấy, thử tìm trong Standard PNMLs
        if not os.path.exists(pnml_path):
            pnml_path = os.path.join(base_dir, "../Standard PNMLs", args.model)

    if not os.path.exists(pnml_path):
        print(f"{Color.RED}❌ File not found: {pnml_path}{Color.RESET}")
        # In thêm thông tin debug đường dẫn để user dễ sửa
        print(f"   Checked: {os.path.abspath(args.model)}")
        print(f"   Checked relative: {os.path.join(os.path.dirname(os.path.abspath(__file__)), args.model)}")
        sys.exit(1)

    solve_task4_complete(pnml_path)