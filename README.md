# MM251 – Petri Net Analysis (Explicit, Symbolic, Deadlock, Optimization)

This repository contains our implementation for the MM-251 / CO2011 assignment on **symbolic and algebraic reasoning in 1-safe Petri nets**.

The project provides:

- Explicit reachability (BFS / DFS)
- Symbolic reachability using BDDs
- Deadlock detection (symbolic intersection + CEGAR reference)
- Optimization over reachable markings
- A unified `main.py` driver to run all tasks from a simple config file

---

## 1. Project Overview

The goal of the assignment is to analyze **1-safe Petri nets** using both **explicit** and **symbolic** techniques, and to reason about:

- **Reachable markings**
- **Deadlock states**
- **Optimal markings** with respect to a linear objective function

Our implementation:

- Parses **PNML** models into an internal `PetriNet` structure.
- Computes reachable markings via **BFS / DFS**.
- Uses **BDD-based symbolic representations** to compute the reachable state space.
- Detects deadlocks by intersecting the reachable set with a “no enabled transition” condition.
- Optionally runs an **optimization pipeline** combining explicit and symbolic analysis.
- Exposes a single entry point: `main.py`, which reads a simple `input.txt` configuration and runs the selected tasks.

---

## 2. Python Version & Dependencies

> ⚠️ **Important:** This project is developed and tested **only** with:
>
> - **Python 3.10.11**

Other versions (3.9, 3.11, 3.12, …) may cause:

- Import errors with BDD / ILP / SAT libraries  
- Behavior differences in typing or 3rd-party APIs  
- Inconsistent benchmark results  

Please make sure your `python` is exactly **3.10.11**.

**Examples:**

- For Windows (py launcher)
```bash
py -3.10 --version   # must print Python 3.10.11
```

- For Unix/macOS (pyenv)
```
pyenv install 3.10.11
pyenv local 3.10.11
python --version     # Python 3.10.11
```

### 2.1. Virtual environment (recommended)

From the repository root:

```bash
python -m venv .venv
```

or:
```
py -3.10 -m venv .venv
```

Activate:
 - For Windows:
```
.\.venv\Scripts\activate
```

 - For Linux/macOS:
```
source .venv/bin/activate
```

Upgrade pip and install dependencies
```
pip install --upgrade pip
pip install -r requirements.txt   # if provided
```

If `requirements.txt` is not present, install the libraries used in your code, e.g.:

- `dd` / `pyeda` – for BDD-based symbolic reasoning
- `pulp` or equivalent – for ILP/optimization
- `lxml` or standard `xml.etree.ElementTree` – for PNML parsing (already used in `parser.py`)

---

## 3. Repository Structure

> Chú ý: Project **không dùng `__init__.py`**, nên không import theo kiểu package (`from source.xxx import ...`).  
> Mỗi file `.py` được chạy như một script bình thường, và `main.py` đóng vai trò entry point chính.

A typical layout:

```text
MM-251-ASSIGNMENT/
├── Standard PNMLs/                    # Example PNML models for testing/benchmarking
│   ├── DocAndPatient.pnml
│   ├── diningPhilosophers.pnml
│   ├── diningPhilosophersFull.pnml
│   ├── file2_token_ring_1safe.pnml
│   ├── file3_access_policy_1safe.pnml
│   └── philo.pnml
│
├── source/
│   ├── parser.py                      # PNML → PetriNet, consistency checks, info printing
│   ├── reachability.py                # Explicit BFS/DFS + pretty printers & utilities
│   ├── symbolic_computation_BDD.py    # BDD-based reachability (dd)
│   ├── symbolic_pyeda.py              # Alternative symbolic engine (PyEDA)
│   ├── deadlock_detection.py          # Symbolic deadlock detection (intersection)
│   ├── deadlock_detection_cegar.py    # CEGAR-based deadlock (reference/comparison)
│   ├── optimization.py                # Optimization over reachable markings (Task 5)
│   └── main.py                        # ⭐ Integrated driver for Tasks 1–5
│
├── test/
│   └── benchmark_runner.py            # Benchmark multiple PNML models (optional)
│
└── README.md                          # This document
```

---

## 4. Assignment Task Mapping

The assignment describes 6 tasks (parsing, explicit reachability, symbolic reachability, deadlock, optimization, report). Roughly:

| Task | Description (from assignment)                          | Implementation in this repo                          |
|------|--------------------------------------------------------|------------------------------------------------------|
| 1    | Parse PNML → internal Petri net                        | `source/parser.py` (`parse_pnml`, `PetriNet`, checks) |
| 2    | Explicit reachability (BFS / DFS)                      | `source/reachability.py` (`reachable_markings_bfs/dfs`) |
| 3    | Symbolic reachability via BDD                          | `source/symbolic_computation_BDD.py` (and `symbolic_pyeda.py`) |
| 4    | Deadlock detection (logical + ILP / CEGAR-style)       | `source/deadlock_detection.py`, `deadlock_detection_cegar.py` |
| 5    | Optimization over reachable markings (optional)        | `source/optimization.py` and `run_task_5` in `main.py` |
| 6    | Report & discussion                                   | Provided as a separate PDF report (not in this repo) |

`main.py` ties these modules together and reproduces the behavior of the individual scripts while allowing everything to be configured via an external `input.txt` file.

---

## 5. Configuration File (`input.txt`)

Instead of passing long command-line arguments, `main.py` uses a simple text configuration file.

### 5.1. Format

`main.py` expects a file with key–value pairs, one per line:

- Lines can contain comments after `#`
- Keys are case-insensitive
- Supported keys:

| Key             | Meaning                                             | Example                         |
|-----------------|-----------------------------------------------------|---------------------------------|
| `PNML`          | Path to the PNML model                              | `PNML: ../Standard PNMLs/philo.pnml` |
| `Task`          | Which tasks to run (`1–5` or `all`)                 | `Task: all` or `Task: 1,2,4`    |
| `Weight Vector` | Weight specification for optimization (Task 5)      | `Weight Vector: P1=10,P2=5`     |
| `Explicit Method` | Explicit method for Task 2 (`bfs`, `dfs`, `both`) | `Explicit Method: both`         |

### 5.2. Example `input.txt`

```text
# Example configuration for main.py
PNML: ../Standard PNMLs/diningPhilosophers.pnml

# Run all implemented tasks
Task: all

# Optional weights for Task 5 (Optimization)
# If empty, optimization.py will auto-assign weights
Weight Vector: P1=10, P2=5

# Explicit reachability method for Task 2
Explicit Method: both
```

`main.py` will:

- Parse this file using `parse_config_file()`  
- Resolve the PNML path using `resolve_path()` (relative to `main.py` and the current working directory)  
- Run the selected tasks in ascending order (1 → 5)

---

## 6. How to Run

### 6.1. Running the unified driver (`main.py`)

Recommended way to use the project:

1. **Create / edit** a config file, e.g., `input.txt`, as described in [Section 5](#5-configuration-file-inputtxt).
2. From the repository root:

```bash
cd source
python main.py ../input.txt
```

Explanation:

- `main.py` imports `parser`, `reachability`, `symbolic_computation_BDD`, `deadlock_detection`, `optimization` **as plain modules**, not as `source.*`.
- Therefore, it is simplest to:
  - `cd source`
  - Run `python main.py <path-to-input.txt>`

Paths in `PNML:` can be absolute or relative (e.g. `../Standard PNMLs/philo.pnml`).

---

### 6.2. Running individual modules (for debugging / demo)

Each main module can also be run standalone, using its own `argparse` interface.

#### 6.2.1. Explicit reachability (`reachability.py`)

```bash
cd source
python reachability.py --model ../Standard\ PNMLs/philo.pnml --method bfs
# or:
python reachability.py --model ../Standard\ PNMLs/philo.pnml --method dfs
```

#### 6.2.2. Symbolic reachability (`symbolic_computation_BDD.py`)

```bash
cd source
python symbolic_computation_BDD.py --model ../Standard\ PNMLs/philo.pnml
```

This script:

- Runs explicit wrappers (BFS/DFS via `reachability.py`)
- Builds BDD-based reachable set
- Prints statistics (number of states, time, memory usage)

#### 6.2.3. Deadlock detection (`deadlock_detection.py`)

```bash
cd source
python deadlock_detection.py --model ../Standard\ PNMLs/philo.pnml
```

This will:

- Build `S_reach` via BDDs
- Construct the dead condition formula
- Intersect them to detect deadlocks
- Extract one deadlock marking (if any), and pretty-print it

A CEGAR-based implementation (`deadlock_detection_cegar.py`) can be used as a reference or comparison method.

#### 6.2.4. Optimization (`optimization.py`)

```bash
cd source
python optimization.py --model ../Standard\ PNMLs/diningPhilosophers.pnml
# With manual weights:
python optimization.py --model ../Standard\ PNMLs/diningPhilosophers.pnml     --weights "P1=10,P2=5"
```

This script:

- Builds a weight vector either automatically or from the `--weights` string
- Runs explicit search for reachable markings
- Runs symbolic search (BDD)
- Verifies consistency and prints candidate optimal markings

> `main.py` internally calls these functionalities via `run_task_2/3/4/5`, so in normal usage you only need `main.py`.

---

### 6.3. Benchmark runner (`test/benchmark_runner.py`)

There is a separate benchmark script under `test/` (not part of the core assignment API, but useful for evaluation):

```bash
cd test
python benchmark_runner.py --dir "../Standard PNMLs"
```

It:

- Finds all `.pnml` files in the given directory
- For each model:
  - Runs explicit search (BFS/DFS)
  - Runs symbolic reachability
  - Runs deadlock detection (symbolic + CEGAR, if available)
- Prints three well-formatted tables:
  - Reachability analysis (explicit vs symbolic)
  - Symbolic deadlock results
  - Performance comparison CEGAR vs symbolic intersection

> Lưu ý: script này chỉnh `sys.path` để truy cập code trong `../source`.  
> Do project **không dùng `__init__.py`**, không nên chạy kiểu `python -m test.benchmark_runner`; hãy chạy trực tiếp file như trên.

---

## 7. Adding New PNML Models

To analyze a new Petri net:

1. **Add your PNML file**  
   Put your `.pnml` file into:

   ```text
   Standard PNMLs/
   ```

   For example: `Standard PNMLs/my_model.pnml`.

2. **Update your config (`input.txt`)**  
   Set the `PNML` field to point to your new model:

   ```text
   PNML: ../Standard PNMLs/my_model.pnml
   Task: all
   Explicit Method: both
   ```

3. **Run via `main.py`**

   ```bash
   cd source
   python main.py ../input.txt
   ```

4. (Optional) **Run benchmarks** on a folder of PNMLs:

   ```bash
   cd test
   python benchmark_runner.py --dir "../Standard PNMLs"
   ```

The parser in `parser.py` is designed to work with standard 1-safe PNML files:

- Places, transitions, arcs are extracted from the XML tree.
- Initial marking is read from `initialMarking` nodes.
- Some consistency checks are performed (e.g., dead transitions, missing arcs).

---

## 8. Implementation Notes

- **No package-style imports**

  - There is **no `__init__.py`** in `source/` or `test/`.
  - All imports are simple module imports: `import parser`, `import reachability`, …
  - This is intentional: the project is meant to be run with simple `python <file>.py` calls, not as an installed package.

- **Internal data model**

  - `parser.py` defines classes such as `Place`, `Transition`, `Arc`, `PetriNet`.
  - The Petri net stores:
    - A dictionary of places
    - A dictionary of transitions
    - Input/output incidence via `input_arcs`, `output_arcs`
    - Initial marking as a mapping from places to token counts

- **Explicit reachability**

  - `reachability.py` works on `PetriNet` and uses BFS/DFS to generate reachable markings.
  - Markings are represented as tuples/vectors in a fixed place order.
  - Helper functions:
    - `build_place_index`, `auto_group_places`, `pretty_marking_vec`, `print_reachability`.

- **Symbolic reachability**

  - `symbolic_computation_BDD.py` encodes each place as a Boolean variable (1-safe).
  - Markings correspond to assignments of these variables.
  - Uses a BDD manager to compute the reachable set via fixpoint iteration.

- **Deadlock logic**

  - `deadlock_detection.py` builds a BDD formula representing the “no enabled transition” condition.
  - Deadlock set = `S_reach ∧ Dead_Condition`.
  - An example marking is extracted from the BDD and converted back into a human-readable format using reachability helpers.

- **Optimization**

  - `optimization.py` defines weight parsing, automatic weight assignment, and a full pipeline that combines explicit and symbolic results.
  - `main.py` calls into this pipeline from `run_task_5`.

---

## 9. Limitations & Assumptions

- The code assumes **1-safe Petri nets**; there is no full general safety-checker.
- Very large models may cause:
  - State space explosion in explicit reachability.
  - Memory issues in BDD-based symbolic reachability.
- Python version is **strictly pinned** to `3.10.11` for stability.
- The project is not packaged as a Python module; all scripts are run directly.

---

## 10. Credits

- Course: **MM-251 / CO2011 – Mathematical Modeling**  
- Assignment theme: *Symbolic and Algebraic Reasoning in Petri Nets*  
- Instructor: *[your course instructor / supervisor]*  
- Implementation: *[Your group name, member names & student IDs]*  
- Tools:
  - Python **3.10.11**
  - BDD/ILP libraries (`dd`, `pyeda`, `pulp`, …) as used in the codebase
