# =============================================================
# deadlock_detection.py
# Compatible with Custom BDD Class (Task 3)
# =============================================================

import pulp
import time
import os

try:
    from pnml_parser import parse_pnml
except ImportError:
    from parser import parse_pnml

from symbolic_computation_BDD import run_symbolic_search


def check_deadlock_custom(net, reach_node, bdd_manager):
    print("\n=== TASK 4: CHECK DEADLOCK (ILP + Custom BDD) ===")
    start_time = time.perf_counter()
    place_names = list(net.places.keys())

    # Tái tạo lại mapping tên biến (khớp với logic trong Task 3)
    # Task 3 đặt tên biến là "x_PlaceName"
    curr_vars_map = {p: f"x_{p}" for p in place_names}

    # --- ILP PART ---
    prob = pulp.LpProblem("Deadlock_Finder", pulp.LpMinimize)
    lp_vars = {p: pulp.LpVariable(f"m_{p}", cat=pulp.LpBinary) for p in place_names}
    prob += 0

    for t_id, _ in net.transitions.items():
        inputs = [p for (p, w) in net.input_arcs.get(t_id, [])]
        if inputs:
            prob += pulp.lpSum([lp_vars[p] for p in inputs]) <= len(inputs) - 1

    iteration = 0
    while True:
        iteration += 1
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if status != pulp.LpStatusOptimal:
            print("✅ CONCLUSION: No Deadlock found (ILP Infeasible).")
            print(f"   Total time: {time.perf_counter() - start_time:.4f}s")
            return

        candidate = {}
        for p in place_names:
            val = pulp.value(lp_vars[p])
            candidate[p] = 0 if val is None else int(val)

        # --- BDD PART (Viết lại cho Custom BDD) ---
        # Custom BDD không dùng toán tử &, ~ mà dùng hàm .land(), .lnot()

        # 1. Tạo Cube (Khối) đại diện cho candidate
        cube_node = bdd_manager.const(True)  # Node 1 (True)

        for p in place_names:
            var_name = curr_vars_map[p]
            var_node = bdd_manager.var(var_name)  # Lấy node biến

            if candidate[p] == 1:
                # cube = cube AND var
                cube_node = bdd_manager.land(cube_node, var_node)
            else:
                # cube = cube AND (NOT var)
                not_var_node = bdd_manager.lnot(var_node)
                cube_node = bdd_manager.land(cube_node, not_var_node)

        # 2. Kiểm tra giao nhau: Reach AND Cube
        intersection_node = bdd_manager.land(reach_node, cube_node)

        # Trong Custom BDD, Node 0 là False. Nếu kết quả != 0 nghĩa là có giao nhau.
        if intersection_node != 0:
            print(f"❌ REAL DEADLOCK FOUND!")
            print(f"   At iteration: {iteration}")
            print(f"   Dead marking: {candidate}")
            print(f"   Execution time: {time.perf_counter() - start_time:.4f}s")
            return
        else:
            # Canonical Cut
            vars_1 = [lp_vars[p] for p in place_names if candidate[p] == 1]
            vars_0 = [lp_vars[p] for p in place_names if candidate[p] == 0]
            if len(vars_1) > 0:
                prob += (pulp.lpSum(vars_1) - pulp.lpSum(vars_0)) <= len(vars_1) - 1
            else:
                prob += pulp.lpSum(lp_vars.values()) >= 1


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="../Standard PNMLs/file1_cabines_1safe.pnml")
    args = parser.parse_args()

    # Xử lý đường dẫn
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pnml_path = os.path.normpath(os.path.join(base_dir, args.model))

    if os.path.exists(pnml_path):
        print(f"📂 Reading file: {pnml_path}")
        net = parse_pnml(pnml_path)

        print("--> Running Task 3 (Custom BDD) to get Reachable data...")

        # [THAY ĐỔI 2] Gọi hàm run_symbolic_search và hứng 5 giá trị trả về
        # Hàm này trả về: (count, elapsed, peak_mem, S, bdd_manager)
        _, _, _, Reach_Node, bdd_mgr = run_symbolic_search(net)

        print("--> Task 3 data obtained. Switching to Task 4.")

        # Truyền dữ liệu sang hàm kiểm tra mới
        check_deadlock_custom(net, Reach_Node, bdd_mgr)

    else:
        print(f"❌ Error: File not found at {pnml_path}")