// Saves what a reviewer did, so it survives a change of browser.
//
// The marks and replies used to live only in localStorage, which is per-device:
// mark forty emails on the demo laptop and the phone still shows none of them.
// This file puts the same records in Postgres, keyed to whoever is signed in.
//
// DESIGN: localStorage stays authoritative for rendering, and the database is a
// background mirror. Two reasons. The page builds its state synchronously at
// load (`marks: loadMarks()`), so an async read there would mean rewriting the
// whole startup path. And the app is meant to open "with no backend, no key and
// no network" - if a paused free-tier database could stop a mark registering,
// that promise is gone. So every write lands locally first and is pushed after.
//
// Signed out, unconfigured, or offline, every function here is a no-op and the
// app behaves exactly as it did before.
(function () {
  "use strict";

  const URL_ = window.SUPABASE_URL || "";
  const KEY = window.SUPABASE_ANON_KEY || "";
  const DEMO = "demo";                       // the 520 shipped emails
  const MARK_OK = "ok", MARK_BACK = "back";  // mirrors the check constraint

  let client = null;

  // The library is loaded as a module by index.html; it may not be ready yet.
  function sb() {
    if (client) return client;
    if (!URL_ || !KEY || !window.supabase) return null;
    client = window.supabase.createClient(URL_, KEY);
    return client;
  }

  async function user() {
    const c = sb();
    if (!c) return null;
    try {
      const { data } = await c.auth.getUser();
      return data && data.user ? data.user : null;
    } catch (_) {
      return null;                            // signed out, or auth unreachable
    }
  }

  // One row per (person, email). `email_ref` is text rather than a foreign key:
  // the 520 demo emails have no row in this database and never will.
  async function pushMark(emailRef, mark) {
    const c = sb(), u = await user();
    if (!c || !u) return;
    try {
      await c.from("reviews")
             .upsert({ user_id: u.id, email_ref: emailRef, source: DEMO, mark: mark },
                     { onConflict: "user_id,email_ref" });
    } catch (error) {
      console.warn("mark not mirrored to the database:", error);
    }
  }

  async function pushReply(emailRef, reply) {
    const c = sb(), u = await user();
    if (!c || !u) return;
    try {
      const { data } = await c.from("reviews")
        .upsert({ user_id: u.id, email_ref: emailRef, source: DEMO, mark: MARK_BACK },
                { onConflict: "user_id,email_ref" })
        .select("id").single();
      if (!data) return;
      await c.from("replies").insert({
        review_id: data.id, to_address: reply.to, subject: reply.subject, body: reply.body,
      });
    } catch (error) {
      console.warn("reply not mirrored to the database:", error);
    }
  }

  async function pushReport(entry) {
    const c = sb(), u = await user();
    if (!c || !u) return;
    try {
      await c.from("reports").insert({
        user_id: u.id, kind: "human", email_ref: entry.about || null,
        title: entry.kind || "note", detail: entry.msg || "",
        rating: entry.rating || null,
      });
    } catch (error) {
      console.warn("report not mirrored to the database:", error);
    }
  }

  // Called once after sign-in: bring this device up to date with the account.
  // Local wins on conflict, because the local mark is the one the person just
  // made and can see on screen.
  async function pull(localMarks) {
    const c = sb(), u = await user();
    if (!c || !u) return null;
    try {
      const { data } = await c.from("reviews").select("email_ref,mark").eq("user_id", u.id);
      if (!data) return null;
      const merged = Object.assign({}, localMarks);
      let added = 0;
      for (const row of data) {
        if (row.mark && !(row.email_ref in merged)) { merged[row.email_ref] = row.mark; added++; }
      }
      return added ? merged : null;
    } catch (error) {
      console.warn("could not read saved marks:", error);
      return null;
    }
  }

  window.Store = { pushMark, pushReply, pushReport, pull, MARK_OK, MARK_BACK };
})();
