// Hash routes: "#/library?gender=F" -> {page: "library", parts: [], query: {gender: "F"}}
const routes = new Map();
let current = null;

export function parseHash(hash = location.hash) {
  const [path, qs = ""] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const query = Object.fromEntries(new URLSearchParams(qs));
  return { page: parts[0] || "library", parts: parts.slice(1), query };
}

export function route(name, page) { routes.set(name, page); }
export function go(path) { location.hash = path.startsWith("#") ? path : "#/" + path.replace(/^\//, ""); }
export function setQuery(query, replace = true) {
  const { page, parts } = parseHash();
  const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)).toString();
  const hash = "#/" + [page, ...parts].join("/") + (qs ? "?" + qs : "");
  if (replace) history.replaceState(null, "", hash); else location.hash = hash;
}

export function start(mount, onChange) {
  async function render() {
    const r = parseHash();
    const page = routes.get(r.page) || routes.get("404");
    if (current && current.unmount) current.unmount();
    mount.scrollTop = 0;
    current = page;
    document.querySelectorAll("[data-route]").forEach((a) => a.setAttribute("aria-current", a.dataset.route === r.page ? "page" : "false"));
    onChange && onChange(r, page);
    await page.mount(mount, r);
  }
  window.addEventListener("hashchange", render);
  return render();
}
export const currentPage = () => current;
