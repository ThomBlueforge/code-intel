"use client";

import {
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError, type GraphData, getGraph } from "@/lib/api";
import { computeLayout } from "@/lib/graphLayout";
import { Button, EmptyState, Panel, Spinner } from "./ui";

const W = 960;
const H = 560;

interface Props {
  repoPath: string;
  initialSymbol?: string | null;
}

export function Graph({ repoPath, initialSymbol }: Props) {
  const [symbol, setSymbol] = useState(initialSymbol ?? "");
  const [depth, setDepth] = useState(1);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [viewTf, setViewTf] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const load = useCallback(
    async (name: string, d: number) => {
      const q = name.trim();
      if (!q) return;
      setLoading(true);
      setError(null);
      try {
        const g = await getGraph(repoPath, q, d);
        setData(g);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [repoPath],
  );

  useEffect(() => {
    setData(null);
    setError(null);
    setSymbol(initialSymbol ?? "");
    if (initialSymbol) void load(initialSymbol, 1);
  }, [repoPath, initialSymbol, load]);

  // Non-passive wheel so zoom doesn't scroll the page.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handler = (ev: WheelEvent) => {
      ev.preventDefault();
      setViewTf((v) => ({
        ...v,
        k: Math.max(0.3, Math.min(3, v.k * (ev.deltaY < 0 ? 1.1 : 0.9))),
      }));
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [data]);

  const focusId = useMemo(() => {
    if (!data) return null;
    return (
      data.nodes.find((n) => n.name === data.focus)?.id ??
      data.nodes[0]?.id ??
      null
    );
  }, [data]);

  const layout = useMemo(
    () => (data ? computeLayout(data.nodes, data.edges, W, H, focusId) : null),
    [data, focusId],
  );

  // Fit the computed layout into the viewBox (centre + scale with padding).
  const fit = useMemo(() => {
    if (!layout || layout.size === 0) return { x: 0, y: 0, k: 1 };
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const p of layout.values()) {
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
    const pad = 90;
    const bw = maxX - minX || 1;
    const bh = maxY - minY || 1;
    const k = Math.max(0.4, Math.min(1.6, Math.min((W - pad * 2) / bw, (H - pad * 2) / bh)));
    return {
      x: W / 2 - ((minX + maxX) / 2) * k,
      y: H / 2 - ((minY + maxY) / 2) * k,
      k,
    };
  }, [layout]);

  useEffect(() => {
    setViewTf(fit);
  }, [fit]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void load(symbol, depth);
  };

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: event.clientX, y: event.clientY, vx: viewTf.x, vy: viewTf.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const start = drag.current;
    if (!start) return;
    setViewTf((v) => ({
      ...v,
      x: start.vx + (event.clientX - start.x),
      y: start.vy + (event.clientY - start.y),
    }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const refocus = (name: string) => {
    setSymbol(name);
    void load(name, depth);
  };

  return (
    <div className="stack-lg">
      <Panel
        eyebrow="Structural graph"
        title="Graph explorer"
        actions={
          <form className="graph-form" onSubmit={onSubmit}>
            <input
              className="search-input"
              placeholder="Symbol name"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
            />
            <select
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
              aria-label="Neighbourhood depth"
            >
              <option value={1}>depth 1</option>
              <option value={2}>depth 2</option>
              <option value={3}>depth 3</option>
            </select>
            <Button variant="accent" type="submit" disabled={loading}>
              {loading ? <Spinner /> : "Explore"}
            </Button>
          </form>
        }
      >
        {error ? <div className="notice notice-danger">{error}</div> : null}
        <div className="graph-legend">
          <span className="legend-item">
            <span className="legend-line legend-static" /> static
          </span>
          <span className="legend-item">
            <span className="legend-line legend-llm" /> llm
          </span>
          <span className="legend-hint">
            scroll to zoom · drag to pan · click a node to refocus
          </span>
        </div>

        {!data || !layout ? (
          loading ? (
            <div className="loading-block">
              <Spinner label="Building graph…" />
            </div>
          ) : (
            <EmptyState title="Explore the structural graph">
              Enter a symbol name to see its neighbourhood.
            </EmptyState>
          )
        ) : data.nodes.length === 0 ? (
          <EmptyState title="No neighbourhood found" />
        ) : (
          <div className="graph-canvas">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${W} ${H}`}
              className="graph-svg"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
            >
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="18"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M0,0 L10,5 L0,10 z" fill="var(--faint)" />
                </marker>
              </defs>
              <g transform={`translate(${viewTf.x} ${viewTf.y}) scale(${viewTf.k})`}>
                {data.edges.map((edge, i) => {
                  const a = layout.get(edge.source);
                  const b = layout.get(edge.target);
                  if (!a || !b) return null;
                  const isStatic = edge.origin === "STATIC_ANALYSIS";
                  const active = hover === edge.source || hover === edge.target;
                  return (
                    <line
                      key={`${edge.source}-${edge.target}-${i}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      className={`edge${isStatic ? " edge-static" : " edge-llm"}${
                        active ? " is-active" : ""
                      }`}
                      markerEnd="url(#arrow)"
                    />
                  );
                })}
                {data.nodes.map((node) => {
                  const p = layout.get(node.id);
                  if (!p) return null;
                  const isFocus = node.id === focusId;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${p.x} ${p.y})`}
                      className={`gnode${isFocus ? " is-focus" : ""}`}
                      onMouseEnter={() => setHover(node.id)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => refocus(node.name)}
                    >
                      <circle r={isFocus ? 9 : 6} className="gnode-dot" />
                      <text x={12} y={4} className="gnode-label">
                        {node.name}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
            <div className="graph-meta mono">
              {data.nodes.length} nodes · {data.edges.length} edges · focus{" "}
              {data.focus}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
