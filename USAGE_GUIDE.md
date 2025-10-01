# XcodeLibPlot – Usage Guide

This document provides a complete guide to the CLI parameters available in **XcodeLibPlot 1.3**, with explanations and usage examples.

---

## 📌 Basic Usage

```bash
python3 XcodeLibPlot_1.3.py --path /path/to/project --output deps_graph
```

This scans the Xcode project/workspace, analyzes dependencies, and generates a dependency graph.

---

## ⚙️ CLI Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--path` | `str` | *required* | Root path of the project/repository (if omitted, tool will prompt) |
| `--output` | `str` | `xcode_deps_graph` | Base output filename (without extension) |
| `--no-render` | flag | `False` | Do not generate PNG/SVG (only `.dot` file) |
| `--no-cycle-highlight` | flag | `False` | Do not highlight cycles in red |
| `--no-system-highlight` | flag | `False` | Do not highlight system frameworks differently |
| `--fail-on-cycles` | flag | `False` | Exit with code 2 if dependency cycles are found |
| `--split-only` | flag | `False` | Generate only per-framework views (skip global graph) |
| `--json-out` | `str` | None | Path to optional JSON export file |
| `--include-target` | `regex (repeatable)` | `[]` | Regex of targets to include |
| `--exclude-target` | `regex (repeatable)` | `[]` | Regex of targets to exclude |
| `--include-lib` | `regex (repeatable)` | `[]` | Regex of libraries to include |
| `--exclude-lib` | `regex (repeatable)` | `[]` | Regex of libraries to exclude |
| `--include-suffix` | `str (repeatable)` | `[]` | File suffixes to include (`.framework`, `.a`, `.tbd`, `.dylib`, spm, …) |
| `--exclude-suffix` | `str (repeatable)` | `[]` | File suffixes to exclude |
| `--split-by-framework` | flag | `False` | Export one graph per framework/library |
| `--split-dir` | `str` | `<output>_by_framework` | Output directory for per-framework graphs |
| `--split-include-target-deps` | flag | `False` | Include target→target edges in per-framework views |
| `--split-include-peer-libs` | flag | `False` | Include other libraries linked by the same targets |
| `--split-max` | `int` | `0` | Limit the number of frameworks (0 = all) |
| `--split-min-degree` | `int` | `1` | Minimum number of targets linking a framework |
| `--only-cycles` | flag | `False` | Generate only cycle subgraphs |
| `--rankdir` | `str` | `LR` | Graphviz rank direction (`LR`, `TB`) |
| `--title` | `str` | None | Custom graph title |
| `--subtitle` | `str` | None | Custom graph subtitle |
| `--ignore-duplicates` | flag | `False` | Do not warn about duplicate dependencies |
| `--merge-spm-products` | flag | `False` | Merge SPM product dependencies under package name |
| `--collapse-suffix` | `str (repeatable)` | `[]` | Collapse multiple suffixes into one node |
| `--highlight-lib` | `regex (repeatable)` | `[]` | Regex of libraries to highlight |
| `--highlight-target` | `regex (repeatable)` | `[]` | Regex of targets to highlight |
| `--log-file` | `str` | None | Save log output to file |
| `--verbose` | flag | `False` | Enable verbose logging |
| `--version` | flag | `False` | Show tool version and exit |
| `--help` | flag | - | Show usage help and exit |

---

## 📝 Examples

### Generate a simple dependency graph
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp
```

### Generate graph but skip PNG/SVG (only DOT file)
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp --no-render
```

### Export also to JSON
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp --json-out deps.json
```

### Include only specific targets
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp --include-target ".*App" --include-target ".*Tests"
```

### Exclude system libraries
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp --no-system-highlight
```

### Generate one graph per framework
```bash
python3 XcodeLibPlot_1.3.py --path ./MyApp --split-by-framework --split-dir ./graphs
```

---

## 🔍 Notes

- Regex-based parameters (`--include-*`, `--exclude-*`, `--highlight-*`) can be repeated multiple times.
- When both *include* and *exclude* are provided, **excludes take precedence**.
- The tool requires `plutil` (macOS) and Graphviz (`dot`) installed in the system.

---
