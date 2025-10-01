# 🍏 Xcode Dependencies Graph — Analyzer & Visualizer

**XcodeLibPlot** is a Python script that analyzes Xcode projects and generates dependency graphs between targets and libraries.  
It highlights cycles, distinguishes between system and third-party frameworks, supports advanced filtering, and can export results in multiple formats: **graphical** (DOT/PNG/SVG), **textual** (logs), **machine-readable** (JSON), and **per-framework** outputs in dedicated folders.

> Features include Apple-style logs with emoji, cycle detection 🔴, system vs third-party framework coloring, advanced filters, per-framework split, customizable colors, and CI integration with fail-on-cycles.

---

## ✨ Main Features

- 🔍 Recursive scan of `.xcodeproj` and `.xcworkspace`
- 🧠 Robust parsing of `project.pbxproj` via `plutil` (with textual fallback if unavailable)
- 🧱 Dependency detection: **Target → Framework/Library**, **Target → Target**, **SwiftPM (SPM)**
- 🔁 **Cycle detection** (SCC, Tarjan’s algorithm) with red highlighting on nodes/edges
- 🧭 **Legend** in DOT output with shape and color explanations
- 🌐 **JSON export** (`--json-out`) including `has_cycles` and `cycles_count`
- 📝 Text logs with emoji + final **CYCLES: PRESENT/ABSENT** banner
- 📄 **Cycle summary** also exported to `<output>.cycles.txt` (useful for CI pipelines)
- 🖼️ **Per-framework split**: one clean view per framework in separate folders
- 🎛 **Advanced filters** for target/library/suffix, with separate highlighting for system vs 3rd-party
- 🎨 **Customizable colors** via CLI
- 🚦 **CI-friendly**: `--fail-on-cycles` → non-zero exit code if cycles are found

---

## 📦 Requirements

- macOS with **Xcode Command Line Tools** (`plutil` included)
- **Graphviz** for PNG/SVG rendering (optional but recommended)

```bash
brew install graphviz
dot -V
```

## 🚀 Quick Usage
# Analyze an Xcode project and generate dependency graphs
python3 XcodeLibPlot.py --path /path/to/MyApp

⚙️ Key CLI Options

--path → project/repo root to analyze

--output → base output filename (default: xcode_deps_graph)

--json-out → also export to JSON

--no-render → only generate .dot, skip PNG/SVG

--split-by-framework → one graph per framework

--include-* / --exclude-* → regex filters for targets/libraries

👉 See USAGE_GUIDE.md
 for the full list of parameters.

