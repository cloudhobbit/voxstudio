// Linked-slider maths for the Mixer: shares always total 100 %, locked voices keep theirs.
// parts: [{id, w (0..1), locked}]. Returns a new array.
export function setShare(parts, index, value) {
  const next = parts.map((p) => ({ ...p }));
  const lockedOther = next.reduce((s, p, i) => s + (i !== index && p.locked ? p.w : 0), 0);
  const free = next.filter((p, i) => i !== index && !p.locked);
  value = Math.max(0, Math.min(1 - lockedOther, value));
  next[index].w = value;
  const remaining = Math.max(0, 1 - lockedOther - value);
  const freeTotal = free.reduce((s, p) => s + p.w, 0);
  for (const p of free) p.w = freeTotal > 1e-9 ? (p.w / freeTotal) * remaining : remaining / free.length;
  return normalise(next);
}
export function normalise(parts) {
  const total = parts.reduce((s, p) => s + p.w, 0) || 1;
  return parts.map((p) => ({ ...p, w: Math.round((p.w / total) * 1000) / 1000 }));
}
export function evenSplit(parts) { return parts.map((p) => ({ ...p, w: 1 / parts.length, locked: false })); }
export function toSpec(parts) { return parts.length === 1 ? parts[0].id : parts.map((p) => `${p.id}:${p.w.toFixed(2)}`).join(","); }
export function fromSpec(spec) {
  const parts = spec.split(",").map((s) => { const [id, w] = s.trim().split(":"); return { id, w: w ? +w : 1, locked: false }; });
  return normalise(parts);
}
