// A small deterministic force-directed layout (Fruchterman–Reingold-ish) for the
// graph explorer. Neighbourhoods are small, so a few hundred synchronous
// iterations are cheap and avoid pulling in a graph library.

import type { GraphEdge, GraphNode } from "./api";

export interface Point {
  x: number;
  y: number;
}

interface Body extends Point {
  vx: number;
  vy: number;
}

export function computeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
  focusId: string | null,
): Map<string, Point> {
  const out = new Map<string, Point>();
  const count = nodes.length;
  if (count === 0) return out;

  const cx = width / 2;
  const cy = height / 2;
  const radius = count > 1 ? Math.min(width, height) * 0.32 : 0;
  const state = new Map<string, Body>();
  nodes.forEach((n, i) => {
    const angle = (i / count) * Math.PI * 2;
    state.set(n.id, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
    });
  });

  const k = Math.max(60, Math.min(width, height) / Math.sqrt(count + 1));
  const links = edges.filter((e) => state.has(e.source) && state.has(e.target));
  const iterations = count > 80 ? 150 : 300;
  const maxStep = 24;
  const damping = 0.85;

  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < count; i++) {
      const a = state.get(nodes[i].id)!;
      for (let j = i + 1; j < count; j++) {
        const b = state.get(nodes[j].id)!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const d = Math.hypot(dx, dy) || 0.01;
        const rep = (k * k) / (d * d);
        dx /= d;
        dy /= d;
        a.vx += dx * rep;
        a.vy += dy * rep;
        b.vx -= dx * rep;
        b.vy -= dy * rep;
      }
    }
    for (const edge of links) {
      const a = state.get(edge.source)!;
      const b = state.get(edge.target)!;
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      const d = Math.hypot(dx, dy) || 0.01;
      const att = (d * d) / k / d;
      dx *= att;
      dy *= att;
      a.vx -= dx;
      a.vy -= dy;
      b.vx += dx;
      b.vy += dy;
    }
    for (const n of nodes) {
      const p = state.get(n.id)!;
      if (n.id === focusId) {
        p.x = cx;
        p.y = cy;
        p.vx = 0;
        p.vy = 0;
        continue;
      }
      p.x += Math.max(-maxStep, Math.min(maxStep, p.vx));
      p.y += Math.max(-maxStep, Math.min(maxStep, p.vy));
      p.vx *= damping;
      p.vy *= damping;
    }
  }

  for (const n of nodes) {
    const p = state.get(n.id)!;
    out.set(n.id, { x: p.x, y: p.y });
  }
  return out;
}
