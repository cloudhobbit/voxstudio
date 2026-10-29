// The API client. Every error becomes an ApiError with the server's plain-language detail.
import { toast } from "./ui.js";

export class ApiError extends Error {
  constructor(status, detail, body) { super(detail); this.status = status; this.body = body; }
}

async function call(method, path, body, { quiet = false } = {}) {
  let res;
  try {
    res = await fetch(path, { method, headers: body !== undefined ? { "Content-Type": "application/json" } : {},
                              body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch (e) {
    document.dispatchEvent(new CustomEvent("vox:offline"));
    throw new ApiError(0, "Can't reach the server", null);
  }
  document.dispatchEvent(new CustomEvent("vox:online"));
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    let detail = data && data.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
    detail = detail || `${res.status} ${res.statusText}`;
    if (!quiet && res.status !== 409) toast(detail, { kind: "error" });
    throw new ApiError(res.status, detail, data);
  }
  return data;
}

export const api = {
  get: (p, o) => call("GET", p, undefined, o),
  post: (p, b, o) => call("POST", p, b, o),
  put: (p, b, o) => call("PUT", p, b, o),
  patch: (p, b, o) => call("PATCH", p, b, o),
  del: (p, o) => call("DELETE", p, undefined, o),
  /** Poll a job until it finishes; onProgress(job) is called on every poll. */
  async job(jobId, onProgress) {
    for (;;) {
      const job = await call("GET", `/api/jobs/${jobId}`);
      if (onProgress) onProgress(job);
      if (job.status === "done" || job.status === "failed") return job;
      await new Promise((r) => setTimeout(r, job.total > 20 ? 400 : 150));
    }
  },
};

/** Render one line; returns {key, url, duration, cached, words}. Shows the slim progress line while waiting. */
export async function speak(req, opts) {
  document.dispatchEvent(new CustomEvent("vox:busy", { detail: 1 }));
  try { return await api.post("/api/speak", req, opts); }
  finally { document.dispatchEvent(new CustomEvent("vox:busy", { detail: -1 })); }
}
