# Pipeline Editor Library Research (React + Vite)

Date: 2026-03-14

## What we optimized for

You asked for:

1. Locking graph movement during save/read-only.
2. Dragging + nesting (step into pipeline), with hover/highlight affordances.
3. `+` buttons in graph areas to add items.
4. Arrows between parts, ideally animated ("ant lines").
5. Clean serialize/deserialize between graph UI and DB payload.
6. Rich UI inside nodes (icons, styled text, controls).
7. Subtle add/remove/move animations.

## Shortlist (best matches first)

### 1) React Flow (`@xyflow/react`) - Best default for this project

Why it fits:

- **Locking interactions**: global and per-node lock controls via `nodesDraggable`, per-node `draggable`, and related interaction props.
- **Nesting/subflows**: `parentId` + child `extent: 'parent'` supports parent/child structures.
- **Hover/intersection logic**: instance APIs include `getIntersectingNodes` and `isNodeIntersecting` (useful for drag-over highlight and "drop into container" behavior).
- **Inline `+` UI**: custom node components let you embed arbitrary React UI/buttons.
- **Arrows/animated flow**: edge type includes `animated`; custom edge examples show advanced motion (`animateMotion`, Web Animations API).
- **Serialization**: `ReactFlowInstance.toObject()` returns nodes/edges/viewport; official save/restore example is straightforward.
- **Node richness**: custom nodes can include forms/icons/etc., with React-native composition.

Notes:

- Dynamic drag-to-parent with polished UX is achievable, but fully productized examples are in Pro in some cases.
- Best balance of DX + community + modern React ergonomics for Vite.

---

### 2) AntV X6 - Best if you want stronger built-in graph mechanics

Why it fits:

- **Locking/read-only**: `interacting: false` for full lock, or fine-grained `nodeMovable`, `edgeMovable`, etc.
- **Nesting + drag-into-parent**: explicit `embedding.enabled` + `findParent(...)`.
- **Hover/highlighting**: configurable `highlighting` options including embedding and connection states.
- **Inline controls**: supports custom node rendering with React via `@antv/x6-react-shape`.
- **Arrows/animation**: supports animation APIs (Web Animations style), plus CSS/SMIL options.
- **Serialization**: `graph.toJSON()` and `graph.fromJSON(...)` are first-class.
- **Group controls**: docs show expand/collapse button patterns in group nodes.

Notes:

- Very capable, but API surface is broader than React Flow (higher learning curve).
- Great fit if you prioritize graph-engine behavior over React-first simplicity.

---

### 3) Rete.js - Good for "node-editor"/workflow semantics, but more assembly

Why it fits:

- **Read-only mode**: `rete-readonly-plugin` with explicit enable/disable.
- **Nested/scoped graphs**: scopes plugin supports nested structures.
- **React support**: dedicated React renderer/plugin ecosystem.
- **Import/export**: possible, but docs explicitly describe custom import/export handling for complex objects/order.

Notes:

- Strong for programmable workflows; less "drop-in straightforward" than React Flow for typical app-UI graph editors.
- Serialization usually needs deliberate modeling work.

---

### 4) GoJS - Very powerful enterprise option (commercial license)

Why it fits:

- Mature grouping/nesting, React integration (`gojs-react`), rich model-driven diagrams.
- Strong model features and JSON save/load (`Model.toJson` / `Model.fromJson`).

Trade-off:

- Commercial licensing and operational/legal overhead compared to MIT alternatives.

---

### 5) Cytoscape.js - Strong graph engine, weaker fit for rich React node UI

Why it fits:

- Supports compound nodes (`parent`), locking (`lock`/`unlock`), and JSON graph mutation (`cy.json()`).

Trade-off:

- Better for network/graph analysis visuals than rich app-like embedded node UIs with lots of custom React controls.

## Feature coverage matrix

Legend: `Excellent` / `Good` / `Possible`

| Requirement | React Flow | AntV X6 | Rete.js | GoJS | Cytoscape.js |
|---|---|---|---|---|---|
| Lock graph interactions (save/read-only) | Excellent | Excellent | Excellent | Excellent | Good |
| Drag + nest elements | Good | Excellent | Good | Excellent | Good |
| Hover highlight for valid nesting | Good | Excellent | Good | Good | Good |
| Inline `+` buttons in graph regions | Excellent | Excellent | Good | Good | Possible |
| Arrows + animated connectors | Excellent | Excellent | Good | Good | Good |
| Serialize/deserialize graph <-> DB | Excellent | Excellent | Good (custom mapping effort) | Excellent | Good |
| Rich UI inside nodes | Excellent | Excellent | Good | Good | Possible |
| Smooth add/remove animations | Good | Excellent | Good | Good | Good |
| React + Vite integration simplicity | Excellent | Good | Good | Good | Good |
| License simplicity | MIT | MIT | MIT | Commercial | MIT |

## Recommendation

If we optimize for **fastest path to production with React + Vite**, choose **React Flow**.

If we optimize for **deep built-in nesting/interaction controls** and accept a heavier API, choose **AntV X6**.

**Decision**: Option 1 — **React Flow** (`@xyflow/react`).

- Primary recommendation: React Flow.
- Backup/alternative: X6 (if we find ourselves implementing too many custom grouping/nesting mechanics).

## Implementation sketch (recommended stack: React Flow)

1. **State model**
   - Keep canonical app graph as JSON (`nodes`, `edges`, domain metadata).
   - Persist via `toObject()` + domain transform function.

2. **Read-only/save lock**
   - Toggle `nodesDraggable`, `nodesConnectable`, and selection/edit controls from an app `isLocked` state.

3. **Nesting**
   - Use group/container nodes and set child `parentId`.
   - During drag, use intersection helpers to detect valid target container and show hover style.

4. **Inline add controls**
   - Put `+` buttons in custom node components and in floating panel controls where needed.

5. **Arrows + animation**
   - Start with `animated: true` edges.
   - Upgrade selected edges to custom animated edges for "ant line" style.

6. **Node UX polish**
   - Custom node components for icons, chip labels, validation badges, status indicators.
   - Add enter/exit transitions with motion libs (e.g., Framer Motion) around node render lifecycle.

## Sources

- React Flow API reference: https://reactflow.dev/api-reference/react-flow
- React Flow subflows: https://reactflow.dev/learn/layouting/sub-flows
- React Flow custom nodes: https://reactflow.dev/learn/customization/custom-nodes
- React Flow save/restore (`toObject`): https://reactflow.dev/examples/interaction/save-and-restore
- React Flow edge type (`animated`): https://reactflow.dev/api-reference/types/edge
- React Flow animating edges example: https://reactflow.dev/examples/edges/animating-edges
- X6 interaction (embedding/highlighting/interacting): https://x6.antv.antgroup.com/en/tutorial/basic/interacting
- X6 group mechanics: https://x6.antv.antgroup.com/en/tutorial/intermediate/group
- X6 React nodes: https://x6.antv.antgroup.com/en/tutorial/intermediate/react
- X6 serialization: https://x6.antv.antgroup.com/en/tutorial/basic/serialization
- X6 animation: https://x6.antv.antgroup.com/en/tutorial/basic/animation
- Rete readonly plugin API: https://retejs.org/docs/api/rete-readonly-plugin
- Rete import/export guide: https://retejs.org/docs/guides/import-export
- GoJS React integration: https://gojs.net/latest/intro/react.html
- GoJS groups: https://gojs.net/latest/intro/groups.html
- GoJS model save/load (`toJson`/`fromJson`): https://gojs.net/latest/intro/usingModels.html
- GoJS license terms: https://gojs.net/latest/license.html
- Cytoscape docs: https://js.cytoscape.org/
- React Flow license (MIT): https://raw.githubusercontent.com/xyflow/xyflow/main/LICENSE
- X6 license (MIT): https://raw.githubusercontent.com/antvis/X6/master/LICENSE
- Rete license (MIT): https://raw.githubusercontent.com/retejs/rete/master/LICENSE
- Cytoscape.js license (MIT): https://raw.githubusercontent.com/cytoscape/cytoscape.js/master/LICENSE
