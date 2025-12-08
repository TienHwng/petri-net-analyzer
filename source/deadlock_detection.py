# =============================================================
# task4_deadlock_complete.py
# Task 4: Complete Deadlock Detection (Fixed for 'dd' library)
# =============================================================

import os
import sys
import time
import argparse
import collections
from typing import List, Dict, Set, Tuple

# Tăng giới hạn đệ quy (phòng hờ, dù 'dd' xử lý phần lớn ở tầng dưới)
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

    # [CHANGE]: Import từ file symbolic.py (chứa code dùng thư viện dd)
    from symbolic_computation_BDD import run_symbolic_search
except ImportError as e:
    print(f"{Color.RED}❌ Import Error: {e}{Color.RESET}")
    print("Please ensure parser.py, reachability.py, and symbolic.py are available.")
    sys.exit(1)

# Import thư viện PuLP
try:
    import pulp

    HAS_PULP = True
except ImportError:
    HAS_PULP = False
    print(f"{Color.YELLOW}⚠️ Warning: 'pulp' library not found. ILP check skipped.{Color.RESET}")


# =============================================================
# 1. BDD LOGIC: DEADLOCK FORMULATION
# =============================================================

def build_dead_formula(bdd_mgr, net: PetriNet, place_order: List[str], x_ids: List[object]) -> object:
    """
    Xây dựng công thức Deadlock = AND ( NOT (Enabled(t)) )
    """
    pid_to_idx = {pid: i for i, pid in enumerate(place_order)}

    # Trong 'dd', False là bdd.false, nhưng qua Adapter ta dùng logic của nó
    # Tuy nhiên, để khởi tạo biến tích lũy cho OR, ta nên dùng False (0) của BDD
    # bdd_mgr.bdd.false là node False thực sự
    Any_Enabled = bdd_mgr.bdd.false

    for t_id in net.transitions:
        pre = {pid for pid, w in net.input_arcs.get(t_id, [])}
        post = {pid for pid, w in net.output_arcs.get(t_id, [])}

        # Enable condition: Pre places have token (AND x_p)
        # 1-safe assumption: we verify if input places are 1.
        # Output places empty check is optional in pure Petri nets,
        # but required if we treat 1-safe strictly as prohibiting adding to full place.
        # Here we follow standard Enable rule: Only check inputs >= weight.

        # En_t ban đầu là True
        En_t = bdd_mgr.bdd.true

        # Với mỗi place p trong pre-set
        for pid in pre:
            idx = pid_to_idx[pid]
            # En_t = En_t AND x_p
            En_t = bdd_mgr.land(En_t, x_ids[idx])

        # Accumulate: Any_Enabled = Any_Enabled OR En_t
        Any_Enabled = bdd_mgr.lor(Any_Enabled, En_t)

    # Dead = NOT (Any_Enabled)
    return bdd_mgr.lnot(Any_Enabled)


def extract_marking_from_bdd(bdd_mgr, node, place_order: List[str]) -> List[int]:
    """
    Trích xuất 1 nghiệm từ node BDD sử dụng thư viện 'dd'.
    Thay vì DFS thủ công, ta dùng hàm pick() của thư viện.
    """
    if node == bdd_mgr.bdd.false:
        return None

    # 'dd' function pick(u) returns a dict {var_name: True/False}
    # satisfying the formula u.
    assignment = bdd_mgr.bdd.pick(node)

    marking = []
    for pid in place_order:
        var_name = f"x_{pid}"
        # Nếu biến có trong assignment và là True -> 1, ngược lại -> 0
        val = 1 if assignment.get(var_name, False) else 0
        marking.append(val)

    return marking


# =============================================================
# 2. ILP CHECK & 3. TRACE (Giữ nguyên logic, chỉ chỉnh sửa nhỏ)
# =============================================================

def verify_with_ilp(net: PetriNet, place_order: List[str], target_marking: List[int]):
    if not HAS_PULP: return
    print(f"\n{Color.CYAN}--- [ILP] State Equation Verification (using PuLP) ---{Color.RESET}")

    prob = pulp.LpProblem("StateEquationCheck", pulp.LpMinimize)
    t_ids = list(net.transitions.keys())
    sigma_vars = {t: pulp.LpVariable(f"sigma_{t}", lowBound=0, cat=pulp.LpInteger) for t in t_ids}
    prob += pulp.lpSum(sigma_vars.values())

    raw_m0 = [net.places[p].initial_marking for p in place_order]
    m0_safe = [1 if m > 0 else 0 for m in raw_m0]

    for i, p_id in enumerate(place_order):
        delta_p = target_marking[i] - m0_safe[i]
        constraint_expr = 0
        for t in t_ids:
            weight = 0
            for (pid, w) in net.output_arcs.get(t, []):
                if pid == p_id: weight += w
            for (pid, w) in net.input_arcs.get(t, []):
                if pid == p_id: weight -= w
            if weight != 0:
                constraint_expr += weight * sigma_vars[t]
        prob += (constraint_expr == delta_p, f"Flow_Constraint_{p_id}")

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if status == pulp.LpStatusOptimal:
        print(f"{Color.GREEN}✅ State Equation Satisfied!{Color.RESET}")
        fired = []
        for t in t_ids:
            val = pulp.value(sigma_vars[t])
            if val and val > 0:
                t_name = net.transition_id_to_name.get(t, t)
                fired.append(f"{t_name}: {int(val)}")
        print(f"   Parikh Vector: [{', '.join(fired)}]")
    else:
        print(f"{Color.RED}❌ State Equation Violated!{Color.RESET} (Spurious deadlock candidate)")


def find_trace_to_deadlock(net: PetriNet, place_order: List[str], target_marking: List[int]):
    print(f"\n{Color.CYAN}--- [Trace] Reconstructing Firing Sequence (BFS) ---{Color.RESET}")
    start_time = time.perf_counter()

    target_tuple = tuple(target_marking)
    m0_list = [1 if net.places[p].initial_marking > 0 else 0 for p in place_order]  # Ensure 1-safe M0
    m0_tuple = tuple(m0_list)

    if m0_tuple == target_tuple:
        print("   -> Initial marking is already the deadlock.")
        return

    queue = collections.deque([(m0_tuple, [])])
    visited = {m0_tuple}

    # Optimize transition lookup
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
            # Check enabled
            if all(curr_m[idx] == 1 for idx in pre_idxs):
                # Fire
                new_m_list = list(curr_m)
                for idx in pre_idxs: new_m_list[idx] = 0
                for idx in post_idxs: new_m_list[idx] = 1
                new_m = tuple(new_m_list)

                if new_m == target_tuple:
                    final_path = path + [t_id]
                    t_names = [net.transition_id_to_name.get(t, t) for t in final_path]
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
    print(f"📂 Model: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net: return
    net.transition_id_to_name = {t_id: t_obj.name for t_id, t_obj in net.transitions.items()}

    # --- STEP 1: SYMBOLIC REACHABILITY (From Task 3) ---
    print(f"\n{Color.BOLD}STEP 1: REACHABILITY (using 'dd' library){Color.RESET}")
    # run_symbolic_search trả về (count, time, mem, REACHED_NODE, MANAGER_ADAPTER)
    count, t_reach, mem, S_reach, bdd_mgr = run_symbolic_search(net)

    print(f"   -> Reachable States: {count}")
    print(f"   -> Time: {t_reach:.4f}s")

    place_order, _ = build_place_index(net)

    # Tạo danh sách các node biến BDD tương ứng với places (dùng cho công thức Deadlock)
    # bdd_mgr.var(name) gọi xuống dd.var(name)
    x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]

    # --- STEP 2: DEADLOCK DETECTION ---
    print(f"\n{Color.BOLD}STEP 2: DEADLOCK DETECTION{Color.RESET}")
    start_detect = time.perf_counter()

    # 2a. Build Dead Formula
    Dead_Condition = build_dead_formula(bdd_mgr, net, place_order, x_ids)

    # 2b. Intersection: Deadlock = Reachable AND Dead_Condition
    Deadlock_Set = bdd_mgr.land(S_reach, Dead_Condition)

    print(f"   -> Detection Time: {time.perf_counter() - start_detect:.6f}s")

    # Kiểm tra rỗng (so sánh với node False)
    if Deadlock_Set == bdd_mgr.bdd.false:
        print(f"\n{Color.GREEN}✅ NO DEADLOCK FOUND.{Color.RESET}")
    else:
        print(f"\n{Color.RED}❌ DEADLOCK DETECTED!{Color.RESET}")

        # 2c. Extract Example using 'dd' pick
        dead_marking = extract_marking_from_bdd(bdd_mgr, Deadlock_Set, place_order)
        groups = auto_group_places(net)

        print("\n   [Example Deadlock Marking]:")
        print(pretty_marking_vec(dead_marking, net, place_order, groups))

        # --- STEP 3: ILP VERIFICATION ---
        verify_with_ilp(net, place_order, dead_marking)

        # --- STEP 4: TRACE RECONSTRUCTION ---
        find_trace_to_deadlock(net, place_order, dead_marking)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 4 Complete: Deadlock Detection")
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