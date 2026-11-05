// Run with: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import { evenSplit, fromSpec, normalise, setShare, toSpec } from "../../src/voxstudio/app/lib/mixmath.js";

const total = (parts) => parts.reduce((s, p) => s + p.w, 0);
const three = () => [{ id: "a", w: 0.5, locked: false }, { id: "b", w: 0.3, locked: false }, { id: "c", w: 0.2, locked: false }];

test("moving one slider shares the rest out in proportion", () => {
  const next = setShare(three(), 0, 0.8);
  assert.equal(next[0].w, 0.8);
  assert.ok(Math.abs(next[1].w - 0.12) < 0.002 && Math.abs(next[2].w - 0.08) < 0.002);
  assert.ok(Math.abs(total(next) - 1) < 0.005);
});

test("a locked voice keeps its share and caps the others", () => {
  const parts = three();
  parts[1].locked = true;
  const next = setShare(parts, 0, 0.95);
  assert.equal(next[1].w, 0.3);
  assert.equal(next[0].w, 0.7);        // only 70 % was free
  assert.equal(next[2].w, 0);
});

test("sliding to zero and back never divides by zero", () => {
  let parts = setShare(three(), 0, 1);
  assert.deepEqual(parts.map((p) => p.w), [1, 0, 0]);
  parts = setShare(parts, 0, 0.4);
  assert.deepEqual(parts.map((p) => p.w), [0.4, 0.3, 0.3]);
  assert.ok(parts.every((p) => Number.isFinite(p.w)));
});

test("the input is not changed", () => {
  const parts = three();
  setShare(parts, 0, 0.1);
  assert.deepEqual(parts, three());
});

test("specs round-trip", () => {
  assert.equal(toSpec(fromSpec("af_heart:0.6,bf_emma:0.4")), "af_heart:0.60,bf_emma:0.40");
  assert.deepEqual(fromSpec("af_heart,bf_emma").map((p) => p.w), [0.5, 0.5]);
  assert.equal(toSpec([{ id: "af_heart", w: 1 }]), "af_heart");
  assert.deepEqual(normalise([{ id: "a", w: 3 }, { id: "b", w: 1 }]).map((p) => p.w), [0.75, 0.25]);
  assert.ok(evenSplit(three()).every((p) => Math.abs(p.w - 1 / 3) < 1e-9 && !p.locked));
});
