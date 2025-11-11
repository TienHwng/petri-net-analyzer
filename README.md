<!-- # MM-251-Assignment -->
# CO2011 – Mathematical Modeling Assignment
### Symbolic and Algebraic Reasoning in Petri Nets
**Version:** 0.0.2 — HCMUT, Semester 1 (2025–2026)

## Overview
This project implements a small application for analyzing and modeling Petri Nets using symbolic reasoning and integer linear programming (ILP) methods.
The goal is to understand how to represent, explore, and detect deadlocks in concurrent systems.

## Main Tasks
1. **PNML Parser**
   - Read `.pnml` files and build the internal data structure of places, transitions, and arcs.
   - Verify model consistency.

2. **Explicit Reachability (BFS/DFS)**
   - Enumerate all reachable markings using explicit search (BFS or DFS).

3. **Symbolic Reachability using BDD**
   - Encode markings using Binary Decision Diagrams (BDD).
   - Compare time and memory performance with the explicit approach.

4. **Deadlock Detection (ILP + BDD)**
   - Combine ILP and BDD to detect dead markings (states with no enabled transitions).
   - Output a deadlock marking if found; otherwise, report “none”.

5. **Optimization over Reachable Markings**
   - Solve the linear optimization problem `maximize cᵀM` over reachable markings.
   - Use ILP to find the optimal marking if it exists.

## Implementation
- **Languages:** Python / C++ / Java
- **Libraries:**
  - `PyEDA` or `CUDD` for BDD
  - `PuLP` or `Gurobi` for ILP
- **Input:** `.pnml` file (1-safe Petri net)
- **Output:**
  - Total number of reachable markings
  - Deadlock marking (if any)
  - Optimal marking (if any)

## Project Structure
```
MM-251-Assignment/
 ├── README.md
 ├── report.pdf
 ├── main.py / main.cpp / Main.java
 ├── data/        # PNML test files
 └── libs/        # BDD and ILP helper modules
```

## Learning Outcomes
- Understand Petri net theory and its applications.
- Apply symbolic reasoning using BDDs.
- Integrate ILP to detect deadlocks and optimize system states.

## Submission
- Deadline: **23:00, December 5, 2025 (GMT+7)**
- Submission format:
  ```
  Assignment-CO2011-CSE251-{studentIDs}.zip
  ```
