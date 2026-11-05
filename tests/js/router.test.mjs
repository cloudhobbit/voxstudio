import assert from "node:assert/strict";
import { test } from "node:test";

import { parseHash } from "../../src/voxstudio/app/lib/router.js";

test("hash routes split into page, parts and query", () => {
  assert.deepEqual(parseHash("#/library?gender=F&accent=UK"), { page: "library", parts: [], query: { gender: "F", accent: "UK" } });
  assert.deepEqual(parseHash("#/projects/chapter-one"), { page: "projects", parts: ["chapter-one"], query: {} });
  assert.deepEqual(parseHash(""), { page: "library", parts: [], query: {} });
  assert.equal(parseHash("#/workbench?text=Hello%20there%2C%20you").query.text, "Hello there, you");
});
