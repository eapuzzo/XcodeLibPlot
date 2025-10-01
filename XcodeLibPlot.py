#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, TextIO

APPLE = "🍏"
SEARCH = "🔍"
FOLDER = "📁"
WARN = "⚠️"
OK = "✅"
PAINT = "🎨"
RED = "🔴"

# --- Simple tee logger (stdout + file) ---------------------------------------
LOG_FP: Optional[TextIO] = None

def _emit(msg: str, err: bool = False):
    print(msg, file=sys.stderr if err else sys.stdout)
    if LOG_FP:
        try:
            LOG_FP.write(msg + "\n")
        except Exception:
            pass

def log_info(msg: str):
    _emit(f"{APPLE} {msg}")

def log_step(msg: str):
    _emit(f"{SEARCH} {msg}")

def log_warn(msg: str):
    _emit(f"{WARN} {msg}", err=True)

def log_ok(msg: str):
    _emit(f"{OK} {msg}")

# --- Discovery ---------------------------------------------------------------
def find_xcode_containers(root: Path) -> Tuple[List[Path], List[Path]]:
    """Trova tutte le .xcodeproj e .xcworkspace ricorsivamente."""
    projects, workspaces = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        skip_dirs = {".git", "DerivedData", "build", ".build"}
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        p = Path(dirpath)
        for d in dirnames:
            if d.endswith(".xcodeproj"):
                projects.append(p / d)
            elif d.endswith(".xcworkspace"):
                workspaces.append(p / d)
    return projects, workspaces

def plutil_to_json(pbxproj_path: Path) -> Optional[Dict]:
    """
    Converte un project.pbxproj (OpenStep plist) in JSON usando plutil.
    Restituisce il dict JSON oppure None se fallisce.
    """
    try:
        result = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", str(pbxproj_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        log_warn(f"Impossibile convertire con plutil: {pbxproj_path} ({e})")
        return None

def extract_projects_from_workspace(workspace_path: Path) -> List[Path]:
    """
    Estrae i progetti referenziati da un .xcworkspace leggendo contents.xcworkspacedata (XML).
    Ritorna i path (relativi o assoluti) che esistono su disco.
    """
    xml_path = workspace_path / "contents.xcworkspacedata"
    found = []
    if not xml_path.exists():
        return found
    try:
        xml = xml_path.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'<FileRef\s+location="([^"]+)"', xml):
            loc = m.group(1)
            if loc.startswith("group:"):
                rel = loc.split("group:", 1)[1]
                cand = (workspace_path / rel).resolve()
            elif loc.startswith("absolute:"):
                cand = Path(loc.split("absolute:", 1)[1]).resolve()
            else:
                cand = (workspace_path / loc).resolve()
            if cand.exists():
                found.append(cand)
    except Exception as e:
        log_warn(f"Errore leggendo workspace: {workspace_path} ({e})")
    return found

def is_library_like(name_or_path: str) -> bool:
    lowered = name_or_path.lower()
    return any(lowered.endswith(ext) for ext in (".framework", ".a", ".tbd", ".dylib"))

def basename_without_ext(p: str) -> str:
    base = os.path.basename(p)
    if base.endswith(".framework"):
        return base.replace(".framework", "")
    if base.endswith(".tbd") or base.endswith(".dylib") or base.endswith(".a"):
        return os.path.splitext(base)[0]
    return base

def detect_system_framework(fr_obj: Dict) -> bool:
    """
    Euristico per distinguere framework/libreria di sistema da terze parti.
    - path contiene 'System/Library/Frameworks' o '/usr/lib/'
    - sourceTree = SDKROOT o DEVELOPER_DIR
    """
    path = (fr_obj.get("path") or fr_obj.get("name") or "").lower()
    src = (fr_obj.get("sourceTree") or "").upper()
    if "system/library/frameworks" in path:
        return True
    if "/usr/lib/" in path:
        return True
    if src in ("SDKROOT", "DEVELOPER_DIR"):
        return True
    return False

def ext_from_path(p: str) -> str:
    p = p.lower()
    if p.endswith(".framework"):
        return ".framework"
    if p.endswith(".a"):
        return ".a"
    if p.endswith(".tbd"):
        return ".tbd"
    if p.endswith(".dylib"):
        return ".dylib"
    return ""  # unknown / not applicable

def slugify(name: str) -> str:
    s = re.sub(r'[^A-Za-z0-9._-]+', "_", name.strip())
    return s or "item"

# --- Colors ------------------------------------------------------------------
DEFAULT_COLORS = {
    "target_fill": "#e7f1ff",
    "target_stroke": "#3973ff",
    "lib3p_fill": "#fff7e6",
    "lib3p_stroke": "#ffa500",
    "libsys_fill": "#f1f2f6",
    "libsys_stroke": "#8e8e93",
    "cycle_fill": "#ffecec",
    "cycle_stroke": "#ff3b30",
    "focus_fill": "#eafff2",
    "focus_stroke": "#34c759",
    "edge": "#555555",
    "edge_cycle": "#ff3b30",
    "edge_tt": "#9ca3af",
    "edge_peer": "#cfcfcf",
}

def is_hex_color(s: str) -> bool:
    return bool(re.fullmatch(r"#([0-9a-fA-F]{6})", s or ""))

def apply_color_overrides(args) -> Dict[str, str]:
    colors = dict(DEFAULT_COLORS)
    mapping = {
        "color_target_fill": "target_fill",
        "color_target_stroke": "target_stroke",
        "color_lib3p_fill": "lib3p_fill",
        "color_lib3p_stroke": "lib3p_stroke",
        "color_libsys_fill": "libsys_fill",
        "color_libsys_stroke": "libsys_stroke",
        "color_cycle_fill": "cycle_fill",
        "color_cycle_stroke": "cycle_stroke",
        "color_focus_fill": "focus_fill",
        "color_focus_stroke": "focus_stroke",
        "color_edge": "edge",
        "color_edge_cycle": "edge_cycle",
        "color_edge_tt": "edge_tt",
        "color_edge_peer": "edge_peer",
    }
    for arg_name, key in mapping.items():
        val = getattr(args, arg_name, None)
        if val:
            if is_hex_color(val):
                colors[key] = val
            else:
                log_warn(f"Colore non valido '{val}' per --{arg_name.replace('_','-')}. Mantengo default {colors[key]}.")
    return colors

# --- Graph model -------------------------------------------------------------
class Graph:
    def __init__(self):
        self.target_nodes: Set[str] = set()
        self.lib_nodes: Set[str] = set()
        self.edges: Set[Tuple[str, str]] = set()  # (from, to)
        self.annotations: Dict[str, str] = {}     # node -> subtitle

        # Metadata per librerie
        self.lib_meta: Dict[str, Dict] = {}       # name -> {is_system: bool, ext: str}

        # Cycle highlighting
        self.cycle_nodes: Set[str] = set()
        self.cycle_edges: Set[Tuple[str, str]] = set()
        self.cycle_components: List[List[str]] = []  # for logging

    # --- Builders
    def add_target(self, name: str):
        self.target_nodes.add(name)

    def add_lib(self, name: str, subtitle: Optional[str] = None,
                is_system: bool = False, ext: Optional[str] = None):
        self.lib_nodes.add(name)
        if subtitle:
            self.annotations[name] = subtitle
        meta = self.lib_meta.get(name, {})
        if ext is not None:
            meta["ext"] = ext
        if "is_system" not in meta:
            meta["is_system"] = is_system
        else:
            meta["is_system"] = meta["is_system"] or is_system
        self.lib_meta[name] = meta

    def add_edge(self, src: str, dst: str):
        if src and dst:
            self.edges.add((src, dst))

    # --- Graph utils
    def _build_adjacency(self) -> Dict[str, Set[str]]:
        adj: Dict[str, Set[str]] = {}
        for a, b in self.edges:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set())  # ensure key exists
        for n in self.target_nodes | self.lib_nodes:
            adj.setdefault(n, set())
        return adj

    def lib_in_degree(self, lib: str) -> int:
        return sum(1 for (a, b) in self.edges if b == lib and a in self.target_nodes)

    def targets_linking_lib(self, lib: str) -> Set[str]:
        return {a for (a, b) in self.edges if b == lib and a in self.target_nodes}

    def libs_linked_by_targets(self, targets: Set[str]) -> Set[str]:
        return {b for (a, b) in self.edges if a in targets and b in self.lib_nodes}

    # --- Filters (applied post-parse, pre-cycles)
    def apply_filters(self,
                      include_targets: List[re.Pattern],
                      exclude_targets: List[re.Pattern],
                      include_libs: List[re.Pattern],
                      exclude_libs: List[re.Pattern],
                      include_suffixes: Set[str],
                      exclude_suffixes: Set[str],
                      keep_isolated_included_targets: bool = True):
        """
        Applica filtri a nodi/archi. Modifica il grafo in-place.
        """
        def match_any(patterns: List[re.Pattern], text: str) -> bool:
            return any(p.search(text) for p in patterns)

        inc_suf = set(s.lower() for s in include_suffixes)
        exc_suf = set(s.lower() for s in exclude_suffixes)

        def target_allowed(t: str) -> bool:
            if exclude_targets and match_any(exclude_targets, t):
                return False
            if include_targets:
                return match_any(include_targets, t)
            return True

        def lib_allowed(l: str) -> bool:
            if exclude_libs and match_any(exclude_libs, l):
                return False
            if include_libs and not match_any(include_libs, l):
                return False
            meta = self.lib_meta.get(l, {})
            ext = (meta.get("ext") or "").lower()
            ext_key = ext if ext else ""
            # detect 'spm' pseudo-suffix via subtitle repo URL or stored meta
            if l in self.annotations and self.annotations[l] and "http" in self.annotations[l].lower():
                if meta.get("ext") is None:
                    ext_key = "spm"
                    meta["ext"] = "spm"
                    self.lib_meta[l] = meta
            elif meta.get("ext") == "spm":
                ext_key = "spm"
            if inc_suf and ext_key not in inc_suf:
                return False
            if exc_suf and ext_key in exc_suf:
                return False
            return True

        new_edges: Set[Tuple[str, str]] = set()
        for a, b in self.edges:
            if a in self.target_nodes and not target_allowed(a):
                continue
            if b in self.target_nodes and not target_allowed(b):
                continue
            if b in self.lib_nodes and not lib_allowed(b):
                continue
            new_edges.add((a, b))
        self.edges = new_edges

        kept_targets: Set[str] = set()
        kept_libs: Set[str] = set()
        for a, b in self.edges:
            if a in self.target_nodes:
                kept_targets.add(a)
            if b in self.target_nodes:
                kept_targets.add(b)
            if b in self.lib_nodes:
                kept_libs.add(b)
        if keep_isolated_included_targets:
            for t in self.target_nodes:
                if target_allowed(t) and t not in kept_targets:
                    kept_targets.add(t)

        self.target_nodes = kept_targets
        self.lib_nodes = kept_libs
        self.lib_meta = {k: v for k, v in self.lib_meta.items() if k in self.lib_nodes}
        self.annotations = {k: v for k, v in self.annotations.items() if k in self.lib_nodes}

    # --- Cycles (Tarjan SCC)
    def mark_cycles(self):
        adj = self._build_adjacency()
        index = 0
        indices: Dict[str, int] = {}
        low: Dict[str, int] = {}
        stack: List[str] = []
        onstack: Set[str] = set()
        sccs: List[List[str]] = []

        def strongconnect(v: str):
            nonlocal index
            indices[v] = index
            low[v] = index
            index += 1
            stack.append(v)
            onstack.add(v)

            for w in adj.get(v, ()):
                if w not in indices:
                    strongconnect(w)
                    low[v] = min(low[v], low[w])
                elif w in onstack:
                    low[v] = min(low[v], indices[w])

            if low[v] == indices[v]:
                comp: List[str] = []
                while True:
                    w = stack.pop()
                    onstack.remove(w)
                    comp.append(w)
                    if w == v:
                        break
                sccs.append(comp)

        for v in adj.keys():
            if v not in indices:
                strongconnect(v)

        self.cycle_nodes.clear()
        self.cycle_edges.clear()
        self.cycle_components.clear()

        for comp in sccs:
            comp_set = set(comp)
            is_cycle = False
            if len(comp) > 1:
                is_cycle = True
            elif len(comp) == 1:
                v = comp[0]
                if v in adj.get(v, set()):
                    is_cycle = True
            if is_cycle:
                comp_sorted = sorted(comp)
                self.cycle_components.append(comp_sorted)
                self.cycle_nodes.update(comp_sorted)
                for a, b in self.edges:
                    if a in comp_set and b in comp_set:
                        self.cycle_edges.add((a, b))

    # --- DOT Global (con legenda) -------------------------------------------
    def to_dot(self,
               colors: Dict[str, str],
               highlight_cycles: bool = True,
               system_highlight: bool = True) -> str:
        lines = []
        lines.append('digraph XcodeDeps {')
        lines.append('  rankdir=LR;')
        lines.append('  graph [fontname="SF Pro Text", fontsize=10, labelloc="t"];')
        lines.append('  node  [fontname="SF Pro Text", fontsize=10];')
        lines.append(f'  edge  [fontname="SF Pro Text", fontsize=9, color="{colors["edge"]}"];')
        cycles_part = "Cycles: YES" if self.cycle_components else "Cycles: NO"
        lines.append('  label="Xcode Dependencies Graph\\n' +
                     cycles_part + '\\nGenerated: ' +
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '";')
        lines.append("")

        # Targets
        lines.append('  // Targets')
        for t in sorted(self.target_nodes):
            safe_t = t.replace('"', '\\"')
            if highlight_cycles and t in self.cycle_nodes:
                lines.append(
                    f'  "{safe_t}" [shape=ellipse, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];'
                )
            else:
                lines.append(
                    f'  "{safe_t}" [shape=ellipse, style=filled, fillcolor="{colors["target_fill"]}", color="{colors["target_stroke"]}"];'
                )

        # Libraries / Frameworks / SPM
        lines.append('')
        lines.append('  // Frameworks / Libraries / SPM')
        for l in sorted(self.lib_nodes):
            safe_l = l.replace('"', '\\"')
            sub = self.annotations.get(l)
            label = f'{safe_l}\\n({sub})' if sub else safe_l
            meta = self.lib_meta.get(l, {})
            is_sys = bool(meta.get("is_system"))
            if highlight_cycles and l in self.cycle_nodes:
                lines.append(
                    f'  "{safe_l}" [label="{label}", shape=box, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];'
                )
            else:
                if system_highlight and is_sys:
                    lines.append(
                        f'  "{safe_l}" [label="{label}", shape=box, style=filled, fillcolor="{colors["libsys_fill"]}", color="{colors["libsys_stroke"]}"];'
                    )
                else:
                    lines.append(
                        f'  "{safe_l}" [label="{label}", shape=box, style=filled, fillcolor="{colors["lib3p_fill"]}", color="{colors["lib3p_stroke"]}"];'
                    )

        # Edges
        lines.append('')
        lines.append('  // Edges')
        for a, b in sorted(self.edges):
            sa = a.replace('"', '\\"')
            sb = b.replace('"', '\\"')
            if highlight_cycles and (a, b) in self.cycle_edges:
                lines.append(f'  "{sa}" -> "{sb}" [color="{colors["edge_cycle"]}", penwidth=2.2];')
            else:
                lines.append(f'  "{sa}" -> "{sb}";')

        # Legend (cluster)
        lines.append('')
        lines.append('  // Legend')
        lines.append('  subgraph cluster_legend {')
        lines.append('    label="Legend";')
        lines.append('    fontsize=11;')
        lines.append('    color="#cccccc";')
        lines.append('    style=rounded;')
        lines.append(f'    "LEG_Target" [label="Target", shape=ellipse, style=filled, fillcolor="{colors["target_fill"]}", color="{colors["target_stroke"]}"];')
        lines.append(f'    "LEG_Lib3P"  [label="3rd-party Library/Framework", shape=box, style=filled, fillcolor="{colors["lib3p_fill"]}", color="{colors["lib3p_stroke"]}"];')
        lines.append(f'    "LEG_LibSys" [label="System Framework/Library", shape=box, style=filled, fillcolor="{colors["libsys_fill"]}", color="{colors["libsys_stroke"]}"];')
        lines.append(f'    "LEG_CycleNode" [label="Node in cycle", shape=ellipse, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];')
        lines.append(f'    "LEG_Target" -> "LEG_Lib3P" [label="normal edge", fontcolor="{colors["edge"]}", color="{colors["edge"]}"];')
        lines.append(f'    "LEG_Lib3P" -> "LEG_CycleNode" [label="edge in cycle", fontcolor="{colors["edge_cycle"]}", color="{colors["edge_cycle"]}", penwidth=2.2];')
        lines.append('  }')

        lines.append('}')
        return "\n".join(lines)

    # --- DOT (per-framework) -------------------------------------------------
    def to_dot_framework_view(self,
                              framework: str,
                              colors: Dict[str, str],
                              highlight_cycles: bool = True,
                              system_highlight: bool = True,
                              include_target_deps: bool = False,
                              include_peer_libs: bool = False) -> str:
        targets = self.targets_linking_lib(framework)
        peer_libs: Set[str] = set()
        if include_peer_libs and targets:
            peer_libs = self.libs_linked_by_targets(targets) - {framework}

        title = f'Framework view: {framework}\\nTargets: {len(targets)}'
        lines = []
        lines.append('digraph FrameworkView {')
        lines.append('  rankdir=LR;')
        lines.append('  graph [fontname="SF Pro Text", fontsize=10, labelloc="t"];')
        lines.append('  node  [fontname="SF Pro Text", fontsize=10];')
        lines.append(f'  edge  [fontname="SF Pro Text", fontsize=9, color="{colors["edge"]}"];')
        lines.append(f'  label="{title}\\nGenerated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}";')
        lines.append("")

        # Focus library node
        safe_f = framework.replace('"', '\\"')
        sub = self.annotations.get(framework)
        meta = self.lib_meta.get(framework, {})
        is_sys = bool(meta.get("is_system"))
        label = f'{safe_f}\\n({sub})' if sub else safe_f

        if highlight_cycles and framework in self.cycle_nodes:
            lines.append(f'  "{safe_f}" [label="{label}", shape=box, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.2];')
        else:
            if system_highlight and is_sys:
                lines.append(f'  "{safe_f}" [label="{label}", shape=box, style=filled, fillcolor="{colors["libsys_fill"]}", color="{colors["focus_stroke"]}", penwidth=2.0];')
            else:
                lines.append(f'  "{safe_f}" [label="{label}", shape=box, style=filled, fillcolor="{colors["focus_fill"]}", color="{colors["focus_stroke"]}", penwidth=2.0];')

        # Targets
        for t in sorted(targets):
            safe_t = t.replace('"', '\\"')
            if highlight_cycles and t in self.cycle_nodes:
                lines.append(f'  "{safe_t}" [shape=ellipse, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];')
            else:
                lines.append(f'  "{safe_t}" [shape=ellipse, style=filled, fillcolor="{colors["target_fill"]}", color="{colors["target_stroke"]}"];')

        # Peer libs (optional)
        for l in sorted(peer_libs):
            safe_l = l.replace('"', '\\"')
            sub2 = self.annotations.get(l)
            label2 = f'{safe_l}\\n({sub2})' if sub2 else safe_l
            meta2 = self.lib_meta.get(l, {})
            is_sys2 = bool(meta2.get("is_system"))
            if highlight_cycles and l in self.cycle_nodes:
                lines.append(f'  "{safe_l}" [label="{label2}", shape=box, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];')
            else:
                if system_highlight and is_sys2:
                    lines.append(f'  "{safe_l}" [label="{label2}", shape=box, style=filled, fillcolor="{colors["libsys_fill"]}", color="{colors["libsys_stroke"]}"];')
                else:
                    lines.append(f'  "{safe_l}" [label="{label2}", shape=box, style=filled, fillcolor="{colors["lib3p_fill"]}", color="{colors["lib3p_stroke"]}"];')

        # Edges: targets -> framework
        for t in sorted(targets):
            sa = t.replace('"', '\\"')
            if highlight_cycles and (t, framework) in self.cycle_edges:
                lines.append(f'  "{sa}" -> "{safe_f}" [color="{colors["edge_cycle"]}", penwidth=2.2];')
            else:
                lines.append(f'  "{sa}" -> "{safe_f}";')

        # Edges: target -> target (optional)
        if include_target_deps:
            tset = set(targets)
            for a, b in sorted(self.edges):
                if a in tset and b in tset and a in self.target_nodes and b in self.target_nodes:
                    sa = a.replace('"', '\\"')
                    sb = b.replace('"', '\\"')
                    if highlight_cycles and (a, b) in self.cycle_edges:
                        lines.append(f'  "{sa}" -> "{sb}" [color="{colors["edge_cycle"]}", penwidth=2.2];')
                    else:
                        lines.append(f'  "{sa}" -> "{sb}" [color="{colors["edge_tt"]}"];')

        # Edges: targets -> peer libs (optional)
        if include_peer_libs and peer_libs:
            tset = set(targets)
            for a, b in sorted(self.edges):
                if a in tset and b in peer_libs:
                    sa = a.replace('"', '\\"')
                    sb = b.replace('"', '\\"')
                    if highlight_cycles and (a, b) in self.cycle_edges:
                        lines.append(f'  "{sa}" -> "{sb}" [color="{colors["edge_cycle"]}", penwidth=2.2, style=solid];')
                    else:
                        lines.append(f'  "{sa}" -> "{sb}" [color="{colors["edge_peer"]}", style=dashed];')

        # Minimal legend
        lines.append('')
        lines.append('  // Legend')
        lines.append('  subgraph cluster_legend {')
        lines.append('    label="Legend"; fontsize=11; color="#cccccc"; style=rounded;')
        lines.append(f'    "LEG_Target" [label="Target", shape=ellipse, style=filled, fillcolor="{colors["target_fill"]}", color="{colors["target_stroke"]}"];')
        lines.append(f'    "LEG_Focus"  [label="Focus Framework", shape=box, style=filled, fillcolor="{colors["focus_fill"]}", color="{colors["focus_stroke"]}", penwidth=2.0];')
        lines.append(f'    "LEG_CycleNode" [label="Node in cycle", shape=box, style=filled, fillcolor="{colors["cycle_fill"]}", color="{colors["cycle_stroke"]}", penwidth=2.0];')
        lines.append(f'    "LEG_Target" -> "LEG_Focus" [label="normal edge", fontcolor="{colors["edge"]}", color="{colors["edge"]}"];')
        lines.append(f'    "LEG_Focus" -> "LEG_CycleNode" [label="edge in cycle", fontcolor="{colors["edge_cycle"]}", color="{colors["edge_cycle"]}", penwidth=2.2];')
        lines.append('  }')

        lines.append('}')
        return "\n".join(lines)

# --- PBX parsing -------------------------------------------------------------
def parse_pbxproj_dependencies(pbx_json: Dict, graph: Graph):
    objects = pbx_json.get("objects", {})
    file_refs: Dict[str, Dict] = {}
    build_files_to_filerefs: Dict[str, str] = {}
    frameworks_phase_to_files: Dict[str, List[str]] = {}
    target_to_frameworks_phases: Dict[str, List[str]] = {}
    target_names: Dict[str, str] = {}
    target_dependencies: List[Tuple[str, str]] = []

    spm_products: Dict[str, Dict] = {}
    spm_packages: Dict[str, Dict] = {}

    for obj_id, obj in objects.items():
        isa = obj.get("isa", "")
        if isa == "PBXFileReference":
            file_refs[obj_id] = obj
        elif isa == "PBXBuildFile":
            if "fileRef" in obj:
                build_files_to_filerefs[obj_id] = obj["fileRef"]
        elif isa == "PBXFrameworksBuildPhase":
            frameworks_phase_to_files[obj_id] = obj.get("files", []) or []
        elif isa == "PBXNativeTarget":
            target_names[obj_id] = obj.get("name", obj_id)
            phases = obj.get("buildPhases", []) or []
            fps = []
            for ph_id in phases:
                ph = objects.get(ph_id, {})
                if ph.get("isa") == "PBXFrameworksBuildPhase":
                    fps.append(ph_id)
            target_to_frameworks_phases[obj_id] = fps

            deps = obj.get("dependencies", []) or []
            for dep_id in deps:
                dep_obj = objects.get(dep_id, {})
                if dep_obj and dep_obj.get("isa") == "PBXTargetDependency":
                    dep_target = dep_obj.get("target")
                    if dep_target:
                        target_dependencies.append((obj_id, dep_target))

        elif isa == "XCSwiftPackageProductDependency":
            spm_products[obj_id] = {
                "productName": obj.get("productName"),
                "package": obj.get("package"),
            }
        elif isa == "XCRemoteSwiftPackageReference":
            spm_packages[obj_id] = {
                "repositoryURL": obj.get("repositoryURL"),
            }

    for t_id, t_name in target_names.items():
        graph.add_target(t_name)

    for t_id, fps in target_to_frameworks_phases.items():
        t_name = target_names.get(t_id, t_id)
        for fp_id in fps:
            build_files = frameworks_phase_to_files.get(fp_id, [])
            for bf_id in build_files:
                fr_id = build_files_to_filerefs.get(bf_id)
                if not fr_id:
                    continue
                fr = file_refs.get(fr_id, {})
                lib_path = fr.get("path") or fr.get("name") or ""
                if not lib_path:
                    continue
                if is_library_like(lib_path):
                    lib_name = basename_without_ext(lib_path)
                    is_sys = detect_system_framework(fr)
                    ext = ext_from_path(lib_path)
                    graph.add_lib(lib_name, is_system=is_sys, ext=ext)
                    graph.add_edge(t_name, lib_name)

    for t_id, obj in objects.items():
        if obj.get("isa") == "PBXNativeTarget":
            t_name = target_names.get(t_id, t_id)
            ppds = obj.get("packageProductDependencies", []) or []
            for p_id in ppds:
                prod = spm_products.get(p_id)
                if not prod:
                    continue
                pname = prod.get("productName") or f"SPMProduct:{p_id}"
                pkg_id = prod.get("package")
                repo = spm_packages.get(pkg_id, {}).get("repositoryURL")
                subtitle = repo if repo else "Swift Package"
                graph.add_lib(pname, subtitle=subtitle, is_system=False, ext="spm")
                graph.add_edge(t_name, pname)

    for src_id, dst_id in target_dependencies:
        src_name = target_names.get(src_id, src_id)
        dst_name = target_names.get(dst_id, dst_id)
        graph.add_edge(src_name, dst_name)

def process_project(project_path: Path, graph: Graph):
    pbxproj_path = project_path / "project.pbxproj"
    if not pbxproj_path.exists():
        log_warn(f"Manca project.pbxproj in {project_path}")
        return

    log_step(f"Analizzo {pbxproj_path} …")
    pbx_json = plutil_to_json(pbxproj_path)
    if pbx_json is None:
        try:
            raw = pbxproj_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            raw = ""
        libs = set()
        for m in re.finditer(r'path\s*=\s*"?(.*?\.(?:framework|a|tbd|dylib))"?\s*;', raw, flags=re.IGNORECASE):
            libs.add(basename_without_ext(m.group(1)))
        proj_name = project_path.stem
        graph.add_target(f"[{proj_name}]")
        for lib in sorted(libs):
            graph.add_lib(lib, is_system=False, ext=None)
            graph.add_edge(f"[{proj_name}]", lib)
        return

    parse_pbxproj_dependencies(pbx_json, graph)

# --- Rendering ---------------------------------------------------------------
def render_graphviz(output_base: Path) -> None:
    dot_bin = shutil.which("dot")
    if not dot_bin:
        log_warn("Graphviz non trovato (comando 'dot'). Salto la generazione di PNG/SVG.")
        return
    for fmt in ("png", "svg"):
        out_file = f"{output_base}.{fmt}"
        try:
            subprocess.run(
                [dot_bin, "-T", fmt, f"{output_base}.dot", "-o", out_file],
                check=True,
            )
            log_ok(f"Creato: {out_file}")
        except subprocess.CalledProcessError as e:
            log_warn(f"Errore generando {fmt}: {e}")

# --- JSON export -------------------------------------------------------------
def export_json(graph: Graph, json_path: Path, root: Path, filters_meta: Dict, colors: Dict[str, str]):
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "has_cycles": bool(graph.cycle_components),     # chiaro stato cicli
        "cycles_count": len(graph.cycle_components),
        "nodes": {
            "targets": sorted(list(graph.target_nodes)),
            "libraries": [
                {
                    "name": name,
                    "is_system": bool(graph.lib_meta.get(name, {}).get("is_system")),
                    "ext": graph.lib_meta.get(name, {}).get("ext"),
                    "subtitle": graph.annotations.get(name),
                    "in_degree": graph.lib_in_degree(name),
                }
                for name in sorted(graph.lib_nodes)
            ],
        },
        "edges": [{"from": a, "to": b} for (a, b) in sorted(graph.edges)],
        "cycles": {
            "components": graph.cycle_components,
            "edges": [{"from": a, "to": b} for (a, b) in sorted(graph.cycle_edges)],
        },
        "filters": filters_meta,
        "colors": colors,
    }
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    log_ok(f"JSON scritto: {json_path}")

# --- Cycles summary export ---------------------------------------------------
def export_cycles_summary(output_base: Path, cycle_components: List[List[str]]):
    """
    Scrive un file <output>.cycles.txt con stato cicli per uso umano/CI.
    """
    path = Path(str(output_base) + ".cycles.txt")
    has_cycles = bool(cycle_components)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(f"HAS_CYCLES={'true' if has_cycles else 'false'}\n")
        fp.write(f"CYCLES_COUNT={len(cycle_components)}\n")
        if has_cycles:
            for i, comp in enumerate(cycle_components, start=1):
                fp.write(f"CYCLE_{i}={','.join(comp)}\n")
    log_ok(f"Riepilogo cicli scritto: {path}")

# --- Split-by-framework export ----------------------------------------------
def export_split_by_framework(graph: Graph,
                              out_dir: Path,
                              colors: Dict[str, str],
                              highlight_cycles: bool,
                              system_highlight: bool,
                              include_target_deps: bool,
                              include_peer_libs: bool,
                              split_max: int,
                              split_min_degree: int,
                              do_render: bool,
                              split_flat: bool):
    """
    Esporta una vista per-framework.
    - Se split_flat=True: tutti i file in out_dir, con nomi <slug>.* (comportamento precedente)
    - Se split_flat=False (default): crea una sottocartella per ogni framework, es. out_dir/<slug>/<slug>.*
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    libs_sorted = sorted(graph.lib_nodes, key=lambda l: (-graph.lib_in_degree(l), l.lower()))
    if split_min_degree > 1:
        libs_sorted = [l for l in libs_sorted if graph.lib_in_degree(l) >= split_min_degree]
    if split_max and split_max > 0:
        libs_sorted = libs_sorted[:split_max]

    if not libs_sorted:
        log_warn("Nessun framework soddisfa i criteri per lo split-by-framework.")
        return

    dot_bin = shutil.which("dot")
    count = 0
    for lib in libs_sorted:
        deg = graph.lib_in_degree(lib)
        dot_text = graph.to_dot_framework_view(
            framework=lib,
            colors=colors,
            highlight_cycles=highlight_cycles,
            system_highlight=system_highlight,
            include_target_deps=include_target_deps,
            include_peer_libs=include_peer_libs,
        )
        slug = slugify(lib)
        if split_flat:
            base = out_dir / slug
            dot_path = str(base) + ".dot"
            png_path = str(base) + ".png"
            svg_path = str(base) + ".svg"
        else:
            subdir = out_dir / slug
            subdir.mkdir(parents=True, exist_ok=True)
            base = subdir / slug
            dot_path = str(base) + ".dot"
            png_path = str(base) + ".png"
            svg_path = str(base) + ".svg"

        with open(dot_path, "w", encoding="utf-8") as fp:
            fp.write(dot_text)
        log_ok(f'[{deg} tgt] DOT: {dot_path}')

        if do_render and dot_bin:
            try:
                subprocess.run(["dot", "-T", "png", dot_path, "-o", png_path], check=True)
                subprocess.run(["dot", "-T", "svg", dot_path, "-o", svg_path], check=True)
                log_ok(f"Immagini: {png_path} / {svg_path}")
            except subprocess.CalledProcessError as e:
                log_warn(f"Errore rendering per {lib}: {e}")
        count += 1

    log_info(f"Esportazione per-framework completata: {count} elementi in {out_dir}")

# --- Main --------------------------------------------------------------------
def main():
    global LOG_FP

    parser = argparse.ArgumentParser(
        description="Genera un grafo delle relazioni tra framework/librerie in progetti Xcode (ricorsivo)."
    )
    parser.add_argument("--path", type=str, help="Percorso radice del progetto/repo (se omesso, verrà richiesto)")
    parser.add_argument("--output", type=str, default="xcode_deps_graph", help="Base filename output (senza estensione)")
    parser.add_argument("--no-render", action="store_true", help="Non generare PNG/SVG (lascia solo il .dot)")
    parser.add_argument("--no-cycle-highlight", action="store_true", help="Non evidenziare i cicli in rosso")
    parser.add_argument("--no-system-highlight", action="store_true", help="Non evidenziare diversamente i framework di sistema")
    parser.add_argument("--fail-on-cycles", action="store_true", help="Exit code 2 se vengono trovati cicli")
    parser.add_argument("--split-only", action="store_true", help="Genera solo le viste per-framework (salta il grafo globale)")
    # JSON
    parser.add_argument("--json-out", type=str, help="Percorso file JSON da generare (opzionale)")
    # Filters
    parser.add_argument("--include-target", action="append", default=[], help="Regex dei target da includere (ripetibile)")
    parser.add_argument("--exclude-target", action="append", default=[], help="Regex dei target da escludere (ripetibile)")
    parser.add_argument("--include-lib", action="append", default=[], help="Regex dei nomi libreria da includere (ripetibile)")
    parser.add_argument("--exclude-lib", action="append", default=[], help="Regex dei nomi libreria da escludere (ripetibile)")
    parser.add_argument("--include-suffix", action="append", default=[], help="Suffix da includere (es. .framework, .a, .tbd, .dylib, spm)")
    parser.add_argument("--exclude-suffix", action="append", default=[], help="Suffix da escludere (es. .a, .tbd, spm)")
    # Split-by-framework
    parser.add_argument("--split-by-framework", action="store_true", help="Esporta un grafico per ogni framework/libreria")
    parser.add_argument("--split-dir", type=str, help="Directory di output per i grafi per-framework (default: <output>_by_framework)")
    parser.add_argument("--split-include-target-deps", action="store_true", help="Includi archi target→target nelle viste per-framework")
    parser.add_argument("--split-include-peer-libs", action="store_true", help="Includi altre librerie linkate dagli stessi target")
    parser.add_argument("--split-max", type=int, default=0, help="Limita il numero di framework (0 = tutti)")
    parser.add_argument("--split-min-degree", type=int, default=1, help="Min numero di target che linkano il framework (default 1)")
    parser.add_argument("--split-flat", action="store_true", help="Non creare sottocartelle per framework; salva tutto in un'unica cartella")
    # Colors
    parser.add_argument("--color-target-fill", type=str)
    parser.add_argument("--color-target-stroke", type=str)
    parser.add_argument("--color-lib3p-fill", type=str)
    parser.add_argument("--color-lib3p-stroke", type=str)
    parser.add_argument("--color-libsys-fill", type=str)
    parser.add_argument("--color-libsys-stroke", type=str)
    parser.add_argument("--color-cycle-fill", type=str)
    parser.add_argument("--color-cycle-stroke", type=str)
    parser.add_argument("--color-focus-fill", type=str)
    parser.add_argument("--color-focus-stroke", type=str)
    parser.add_argument("--color-edge", type=str)
    parser.add_argument("--color-edge-cycle", type=str)
    parser.add_argument("--color-edge-tt", type=str)
    parser.add_argument("--color-edge-peer", type=str)

    args = parser.parse_args()

    root_path = args.path
    if not root_path:
        root_path = input(f"{FOLDER} Inserisci il percorso radice da analizzare (default = .): ").strip() or "."

    root = Path(root_path).expanduser().resolve()
    output_base = Path(args.output).resolve()
    dot_path = f"{output_base}.dot"
    log_path = f"{output_base}.log"
    json_path = Path(args.json_out).resolve() if args.json_out else None
    split_dir = Path(args.split_dir).resolve() if args.split_dir else Path(str(output_base) + "_by_framework").resolve()

    # Open log file ASAP
    LOG_FP = open(log_path, "w", encoding="utf-8", buffering=1)
    _emit(f"{APPLE} Avvio analisi dipendenze Xcode  •  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _emit(f"{APPLE} Root: {root}")

    if not root.exists():
        log_warn(f"Percorso inesistente: {root}")
        LOG_FP.close()
        sys.exit(1)

    # Colors from CLI
    colors = apply_color_overrides(args)

    projects, workspaces = find_xcode_containers(root)
    log_step(f"Trovati {len(projects)} progetti (.xcodeproj) e {len(workspaces)} workspace (.xcworkspace)")

    referenced_projects: Set[Path] = set()
    for ws in workspaces:
        refs = extract_projects_from_workspace(ws)
        for ref in refs:
            if ref.suffix == ".xcodeproj":
                referenced_projects.add(ref)

    all_projects: Set[Path] = set(projects) | referenced_projects
    if not all_projects:
        log_warn("Nessun .xcodeproj trovato. Nulla da fare.")
        log_ok(f"Log scritto in: {log_path}")
        LOG_FP.close()
        sys.exit(0)

    graph = Graph()
    for proj in sorted(all_projects):
        log_info(f"Elaboro progetto: {proj}")
        process_project(proj, graph)

    # --- Apply filters BEFORE cycle detection
    def compile_regex_list(patterns: List[str]) -> List[re.Pattern]:
        compiled = []
        for p in patterns:
            try:
                compiled.append(re.compile(p))
            except re.error as e:
                log_warn(f"Regex non valida '{p}': {e}")
        return compiled

    include_targets = compile_regex_list(args.include_target)
    exclude_targets = compile_regex_list(args.exclude_target)
    include_libs = compile_regex_list(args.include_lib)
    exclude_libs = compile_regex_list(args.exclude_lib)
    include_suffixes = set(s.lower() for s in args.include_suffix)
    exclude_suffixes = set(s.lower() for s in args.exclude_suffix)

    if include_suffixes:
        include_suffixes = set([s if s in ("spm",) else (s if s.startswith(".") else "." + s) for s in include_suffixes])
    if exclude_suffixes:
        exclude_suffixes = set([s if s in ("spm",) else (s if s.startswith(".") else "." + s) for s in exclude_suffixes])

    graph.apply_filters(
        include_targets=include_targets,
        exclude_targets=exclude_targets,
        include_libs=include_libs,
        exclude_libs=exclude_libs,
        include_suffixes=include_suffixes,
        exclude_suffixes=exclude_suffixes,
        keep_isolated_included_targets=True,
    )

    # --- Cycles
    highlight_cycles = not args.no_cycle_highlight
    if highlight_cycles:
        log_step("Rilevazione cicli (SCC)…")
        graph.mark_cycles()
        if graph.cycle_components:
            log_warn(f"{RED} Trovati {len(graph.cycle_components)} cicli (componenti fortemente connessi):")
            for i, comp in enumerate(graph.cycle_components, start=1):
                internal_edges = sorted([(a, b) for (a, b) in graph.edges if a in comp and b in comp])
                _emit(f"{RED}  • Ciclo #{i}: nodi = {', '.join(comp)}")
                if internal_edges:
                    for (a, b) in internal_edges:
                        _emit(f"{RED}     - {a} → {b}")
        else:
            log_ok("Nessun ciclo rilevato.")
    else:
        log_info("Evidenziazione cicli disattivata (--no-cycle-highlight).")

    # --- Banner chiaro + riepilogo cicli file
    has_cycles = bool(graph.cycle_components)
    cycles_count = len(graph.cycle_components)
    if has_cycles:
        _emit(f"🛑 CICLI: PRESENTI • {cycles_count}")
    else:
        _emit("✅ CICLI: ASSENTI")
    export_cycles_summary(output_base, graph.cycle_components)

    # Exit code handling for CI
    exit_code = 0
    if args.fail_on_cycles and has_cycles:
        log_warn("Abilitato --fail-on-cycles: verrà restituito exit code 2 (dopo la generazione degli output).")
        exit_code = 2

    # --- JSON (optional) – sempre disponibile, anche con --split-only
    if json_path:
        filters_meta = {
            "include_target": args.include_target,
            "exclude_target": args.exclude_target,
            "include_lib": args.include_lib,
            "exclude_lib": args.exclude_lib,
            "include_suffix": sorted(list(include_suffixes)),
            "exclude_suffix": sorted(list(exclude_suffixes)),
            "highlight_cycles": highlight_cycles,
            "system_highlight": (not args.no_system_highlight),
            "split_only": args.split_only,
        }
        export_json(graph, json_path, root, filters_meta, colors)

    # --- Split-by-framework (optional or forced by --split-only)
    do_split = args.split_by_framework or args.split_only
    if do_split:
        log_step("Esportazione per-framework…")
        export_split_by_framework(
            graph=graph,
            out_dir=split_dir,
            colors=colors,
            highlight_cycles=highlight_cycles,
            system_highlight=not args.no_system_highlight,
            include_target_deps=args.split_include_target_deps,
            include_peer_libs=args.split_include_peer_libs,
            split_max=args.split_max,
            split_min_degree=args.split_min_degree,
            do_render=not args.no_render,
            split_flat=args.split_flat
        )

    # --- DOT globale (salta se --split-only)
    if not args.split_only:
        with open(dot_path, "w", encoding="utf-8") as f:
            f.write(graph.to_dot(colors=colors, highlight_cycles=highlight_cycles, system_highlight=not args.no_system_highlight))
        log_ok(f"File DOT generato: {dot_path}")

        if not args.no_render:
            log_info(f"{PAINT} Genero PNG/SVG (se Graphviz è disponibile)…")
            render_graphviz(output_base)
        else:
            log_warn("Rendering disattivato (--no-render).")
    else:
        log_info("Modalità --split-only: salto il grafo globale.")

    # --- Riepilogo log
    _emit("")
    _emit(f"{APPLE} Riepilogo:")
    _emit(f"   - Target:    {len(graph.target_nodes)}")
    _emit(f"   - Librerie:  {len(graph.lib_nodes)}")
    _emit(f"   - Archi:     {len(graph.edges)}")
    _emit(f"   - Nodi ciclo:{len(graph.cycle_nodes)}  •  Archi ciclo:{len(graph.cycle_edges)}")
    log_ok(f"Log scritto in: {log_path}")
    log_ok("Completato!")

    if LOG_FP:
        LOG_FP.close()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
