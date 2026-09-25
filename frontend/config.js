// Address of the backend (backend/app.py). My mailbox reads and replies through it.
// No trailing slash needed - index.html strips one.
//
// A page opened from this machine (localhost) talks to the backend on this machine,
// so a route that is not deployed yet can be tried: before this, a local page called
// the deployed backend and a new route answered 404 there (#156). Start it with
//   uvicorn backend.app:app --port 8000
// Only localhost switches, never a query string or stored value: the page sends the
// Google token to this address, so nothing a link can set may change it.
(function () {
  var DEPLOYED = "https://blockeris-backend.onrender.com";
  var LOCAL = "http://localhost:8000";
  var LOCAL_HOSTS = ["localhost", "127.0.0.1"];
  window.BLOCKERIS_API_BASE = LOCAL_HOSTS.indexOf(location.hostname) === -1 ? DEPLOYED : LOCAL;
})();

// Where the Help panel sends notes for the support team. Leave empty to only save them on the visitor's device.
// Example: window.BLOCKERIS_SUPPORT_EMAIL = "support@example.com";
window.BLOCKERIS_SUPPORT_EMAIL = "";

// Supabase, for saving what a reviewer marked so it survives a change of browser.
// This key is a PUBLISHABLE key and is meant to be public - it ships in every
// browser that opens the page. Row-level security is what protects the data, so
// a leaked key reads nothing it should not. Leave both empty to keep everything
// on the visitor's own device, exactly as before.
window.SUPABASE_URL = "https://wcvvfiywelypxfkncpww.supabase.co";
window.SUPABASE_ANON_KEY = "sb_publishable_DqF-xlPA8laGPWPY0iSA1g_rkerAglB";
