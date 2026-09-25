// Loads the review page's scripts in the order the browser does, in a minimal fake
// browser, and reports anything thrown while the page starts. A function-level test
// cannot see load order: a const read by the first render() before its line had run
// broke the whole page, sign-in included (#168 hotfix).
import { readFileSync } from "node:fs";
import vm from "node:vm";

const frontend = process.argv[2];
const page = readFileSync(`${frontend}/index.html`, "utf8");

function element(tag = "div") {
  const el = {
    tagName: tag.toUpperCase(), style: { setProperty() {} }, dataset: {}, children: [], classList:
      { add() {}, remove() {}, contains: () => false, toggle() {} },
    innerHTML: "", textContent: "", scrollTop: 0, value: "",
    addEventListener() {}, removeEventListener() {}, appendChild(c) { return c; }, remove() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, focus() {},
    getBoundingClientRect: () => ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 }),
    setAttribute() {}, getAttribute: () => null, replaceWith() {}, scrollIntoView() {},
  };
  return el;
}
const listeners = {};
const store = new Map();
const documentStub = {
  documentElement: element("html"), body: element("body"), activeElement: null, visibilityState: "visible",
  getElementById: () => element(), querySelector: () => null, querySelectorAll: () => [],
  createElement: element, addEventListener: (name, fn) => { (listeners[name] ||= []).push(fn); },
};
const windowStub = {
  document: documentStub, location: { hash: "", search: "", pathname: "/", origin: "https://app.example", href: "https://app.example/" },
  history: { replaceState() {} }, navigator: { language: "en", clipboard: {} },
  localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener: (name, fn) => { (listeners[name] ||= []).push(fn); },
  requestAnimationFrame: () => 0, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  performance: { now: () => 0 }, CSS: { escape: s => s }, scrollTo() {}, scrollY: 0,
  fetch: () => new Promise(() => {}), console, URL, URLSearchParams, AbortController, TextEncoder, Intl,
  IntersectionObserver: class { observe() {} disconnect() {} },
  ResizeObserver: class { observe() {} disconnect() {} },
};
windowStub.window = windowStub;
windowStub.self = windowStub;
const context = vm.createContext(windowStub);

const errors = [];
function run(name, source) {
  try { vm.runInContext(source, context, { filename: name }); }
  catch (error) { errors.push(`${name}: ${error.name}: ${error.message}`); }
}
for (const match of page.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
  const [, attrs, inline] = match;
  const src = (attrs.match(/\bsrc="([^"]+)"/) || [])[1];
  if (src && src.startsWith("http")) continue;          // the CDN library: sign-in is off without it, as offline
  if (/type="module"/.test(attrs)) continue;
  run(src || "index.html inline script", src ? readFileSync(`${frontend}/${src}`, "utf8") : inline);
}
for (const fn of listeners.DOMContentLoaded || []) {
  try { fn(); } catch (error) { errors.push(`DOMContentLoaded: ${error.name}: ${error.message}`); }
}
console.log(JSON.stringify(errors));
