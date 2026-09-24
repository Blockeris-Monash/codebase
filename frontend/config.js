// Address of the deployed backend (backend/app.py). My mailbox reads and replies
// through it. No trailing slash needed - index.html strips one.
window.BLOCKERIS_API_BASE = "https://blockeris-backend.onrender.com";

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
