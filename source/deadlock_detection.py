# =============================================================
# deadlock_detection.py (File riêng)
# nhớ tải thư viện PuLp
# =============================================================

import pulp
import time
import os

# 1. Import Parser
try:
    from pnml_parser import parse_pnml
except ImportError:
    from parser import parse_pnml

# 2. IMPORT QUAN TRỌNG: Lấy hàm từ file Task 3
from symbolic_computation_BDD import symbolic_reachability


def check_deadlock_task4(net, reach_bdd, bdd_manager, curr_vars_map):
    print("\n=== TASK 4: CHECK DEADLOCK (ILP + BDD) ===")

    # [FIX] Khởi tạo biến thời gian ngay đầu hàm
    start_time = time.perf_counter()

    place_names = list(net.places.keys())

    # --- PHẦN ILP (Tìm kiếm trạng thái chết về cấu trúc) ---
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
            print("✅ KẾT LUẬN: Không có Deadlock (ILP Infeasible).")
            # In thời gian chạy ngay cả khi không tìm thấy
            print(f"   Tổng thời gian: {time.perf_counter() - start_time:.4f}s")
            return

        # Lấy candidate từ ILP
        candidate = {}
        for p in place_names:
            val = pulp.value(lp_vars[p])
            candidate[p] = 0 if val is None else int(val)

        # --- PHẦN BDD (Kiểm chứng với dữ liệu từ Task 3) ---
        cube = bdd_manager.true
        for p in place_names:
            bdd_var = bdd_manager.var(curr_vars_map[p])
            if candidate[p] == 1:
                cube &= bdd_var
            else:
                cube &= ~bdd_var

        # Kiểm tra giao nhau
        if (reach_bdd & cube) != bdd_manager.false:
            print(f"❌ TÌM THẤY DEADLOCK THỰC SỰ!")
            print(f"   Tại vòng lặp: {iteration}")
            print(f"   Trạng thái chết: {candidate}")
            # [FIX] Lúc này biến start_time đã tồn tại nên sẽ không lỗi nữa
            print(f"   Thời gian chạy: {time.perf_counter() - start_time:.4f}s")
            return
        else:
            # Chặn nghiệm giả
            vars_1 = [lp_vars[p] for p in place_names if candidate[p] == 1]
            vars_0 = [lp_vars[p] for p in place_names if candidate[p] == 0]
            if len(vars_1) > 0:
                prob += (pulp.lpSum(vars_1) - pulp.lpSum(vars_0)) <= len(vars_1) - 1
            else:
                prob += pulp.lpSum(lp_vars.values()) >= 1


# --- HÀM MAIN ĐỂ CHẠY ---
if __name__ == "__main__":
    # Đổi tên file nếu cần
    pnml_file = r"F:\MM-251-Assignment/Standard PNMLs/file1_cabines_1safe.pnml"

    if os.path.exists(pnml_file):
        print(f"📂 Đang đọc file: {pnml_file}")
        net = parse_pnml(pnml_file)

        print("--> Đang chạy Task 3 để lấy dữ liệu Reachable...")
        Reach, bdd_mgr, var_map = symbolic_reachability(net)

        print("--> Đã có dữ liệu từ Task 3. Chuyển sang Task 4.")
        check_deadlock_task4(net, Reach, bdd_mgr, var_map)

        # Dọn dẹp bộ nhớ thủ công để hạn chế lỗi đỏ cuối cùng
        del bdd_mgr

    else:
        print("❌ File không tồn tại")