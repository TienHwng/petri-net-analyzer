# =============================================================
# deadlock_detection.py (Separate File)
# Remember to install PuLP library: pip install pulp
# =============================================================

import pulp
import time
import os

# 1. Import Parser
try:
    from pnml_parser import parse_pnml
except ImportError:
    from parser import parse_pnml

# 2. IMPORTANT IMPORT: Get function from Task 3 file
# Note: symbolic_computation_BDD.py must be in the same folder
from symbolic_computation_BDD import symbolic_reachability


def check_deadlock_task4(net, reach_bdd, bdd_manager, curr_vars_map):
    print("\n=== TASK 4: CHECK DEADLOCK (ILP + BDD) ===")

    # [FIX] Initialize timer at the start of the function
    start_time = time.perf_counter()

    place_names = list(net.places.keys())

    # --- ILP PART (Find Structural Deadlocks) ---
    prob = pulp.LpProblem("Deadlock_Finder", pulp.LpMinimize)
    lp_vars = {p: pulp.LpVariable(f"m_{p}", cat=pulp.LpBinary) for p in place_names}
    prob += 0  # Empty objective function

    for t_id, _ in net.transitions.items():
        inputs = [p for (p, w) in net.input_arcs.get(t_id, [])]
        if inputs:
            # Constraint: sum(tokens) <= input_count - 1
            prob += pulp.lpSum([lp_vars[p] for p in inputs]) <= len(inputs) - 1

    iteration = 0
    while True:
        iteration += 1
        # Solve ILP (suppress log messages)
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if status != pulp.LpStatusOptimal:
            print("✅ CONCLUSION: No Deadlock found (ILP Infeasible).")
            # Print time even if not found
            print(f"   Total time: {time.perf_counter() - start_time:.4f}s")
            return

        # Extract candidate from ILP (handle None values)
        candidate = {}
        for p in place_names:
            val = pulp.value(lp_vars[p])
            candidate[p] = 0 if val is None else int(val)

        # --- BDD PART (Verify with Task 3 data) ---
        cube = bdd_manager.true
        for p in place_names:
            bdd_var = bdd_manager.var(curr_vars_map[p])
            if candidate[p] == 1:
                cube &= bdd_var
            else:
                cube &= ~bdd_var

        # Check Intersection: (Reach from Task 3) & (Candidate from Task 4)
        if (reach_bdd & cube) != bdd_manager.false:
            print(f"❌ REAL DEADLOCK FOUND!")
            print(f"   At iteration: {iteration}")
            print(f"   Dead marking: {candidate}")
            print(f"   Execution time: {time.perf_counter() - start_time:.4f}s")
            return
        else:
            # Block spurious solution (Canonical Cut)
            vars_1 = [lp_vars[p] for p in place_names if candidate[p] == 1]
            vars_0 = [lp_vars[p] for p in place_names if candidate[p] == 0]
            if len(vars_1) > 0:
                prob += (pulp.lpSum(vars_1) - pulp.lpSum(vars_0)) <= len(vars_1) - 1
            else:
                prob += pulp.lpSum(lp_vars.values()) >= 1


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Change filename if needed
    pnml_file = r"F:\MM-251-Assignment/Standard PNMLs/file1_cabines_1safe.pnml"

    if os.path.exists(pnml_file):
        print(f"📂 Reading file: {pnml_file}")
        net = parse_pnml(pnml_file)

        print("--> Running Task 3 to get Reachable data...")
        # Receive 3 return values
        Reach, bdd_mgr, var_map = symbolic_reachability(net)

        print("--> Task 3 data obtained. Switching to Task 4.")
        # Pass data to Task 4
        check_deadlock_task4(net, Reach, bdd_mgr, var_map)

        # Manually clean up BDD manager to avoid exit errors
        del bdd_mgr

    else:
        print("❌ File not found")