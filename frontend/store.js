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
  const MAILBOX = "mailbox";                 // mail read from the person's own Gmail (gmail_<id>)
  const sourceOf = ref => String(ref).startsWith("gmail_") ? MAILBOX : DEMO;
  const MARK_OK = "ok", MARK_BACK = "back";  // mirrors the check constraint
  const REPORT_LIMIT = 200;                  // a queue, not an archive: page it if it ever fills

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

  // supabase-js resolves with `{ data, error }` when the database refuses a request; it
  // does not throw. Every call goes through this, so a refusal reaches a `catch` and is
  // logged instead of looking exactly like success (#147 B2).
  function checked(result) {
    if (result.error) throw result.error;
    return result.data;
  }

  // One row per (person, email). `email_ref` is text rather than a foreign key:
  // the 520 demo emails have no row in this database and never will.
  // True when the row landed, like pushReport.
  async function pushMark(emailRef, mark) {
    const c = sb(), u = await user();
    if (!c || !u) return false;
    try {
      checked(await c.from("reviews")
        .upsert({ user_id: u.id, email_ref: emailRef, source: sourceOf(emailRef), mark: mark },
                { onConflict: "user_id,email_ref" }));
      return true;
    } catch (error) {
      console.warn("mark not mirrored to the database:", error);
      return false;
    }
  }

  async function pushReply(emailRef, reply) {
    const c = sb(), u = await user();
    if (!c || !u) return false;
    try {
      const review = checked(await c.from("reviews")
        .upsert({ user_id: u.id, email_ref: emailRef, source: sourceOf(emailRef), mark: MARK_BACK },
                { onConflict: "user_id,email_ref" })
        .select("id").single());
      checked(await c.from("replies").insert({
        review_id: review.id, to_address: reply.to, subject: reply.subject, body: reply.body,
        sent_at: reply.real ? new Date().toISOString() : null,   // null: the demo Send, nothing went out
      }));
      return true;
    } catch (error) {
      console.warn("reply not mirrored to the database:", error);
      return false;
    }
  }

  // True when the row reached the queue, false when it did not. The page tells
  // the reviewer which, so "Thank you, we got it" is only said when it is true.
  //
  // supabase-js does not throw when the database refuses a row, it resolves with
  // an `error` - so the old version caught nothing, reported nothing, and the
  // page thanked the reviewer for a report that had been rejected.
  async function pushReport(entry) {
    const c = sb(), u = await user();
    if (!c || !u) return false;
    try {
      // The title is what the admin queue lists, so "problem" three times over
      // is a queue nobody can triage. Name the email it is about.
      const kind = entry.kind || "note";
      const title = entry.about ? `${kind} about ${entry.about}` : kind;
      checked(await c.from("reports").insert({
        user_id: u.id, kind: "human", email_ref: entry.about || null,
        title: title, detail: entry.msg || "",
        rating: entry.rating || null,
      }));
      return true;
    } catch (error) {
      console.warn("report not mirrored to the database:", error);
      return false;
    }
  }

  // A reviewer confirmed, dismissed or fixed a field. The correction is kept
  // for the impact numbers; a `report` (dismiss, fix, or undoing one) also goes
  // to the admin queue, because the result on screen no longer matches what
  // the pipeline decided and somebody should know why.
  //
  // True only when every row landed, so the page never says "sent" for a
  // correction the database refused.
  async function pushCorrection(emailRef, correction, report) {
    const c = sb(), u = await user();
    if (!c || !u) return false;
    let landed = true;
    // The report goes first and on its own: the admin hearing about a change
    // must not depend on the corrections table accepting its row.
    if (report) {
      try {
        checked(await c.from("reports").insert({
          user_id: u.id, kind: "human", email_ref: emailRef,
          title: report.title, detail: report.detail, context: report.context || null,
        }));
      } catch (error) {
        console.warn("correction report not filed:", error);
        landed = false;
      }
    }
    try {
      // No `mark` here: correcting a field is not the same as finishing the email.
      const review = checked(await c.from("reviews")
        .upsert({ user_id: u.id, email_ref: emailRef, source: sourceOf(emailRef) },
                { onConflict: "user_id,email_ref" })
        .select("id").single());
      checked(await c.from("corrections").insert({
        review_id: review.id, field: correction.field, kind: correction.kind, side: correction.side || null,
        was: correction.was, corrected: correction.corrected,
      }));
    } catch (error) {
      console.warn("correction not mirrored to the database:", error);
      landed = false;
    }
    return landed;
  }

  // --- the reports queue (/admin) -----------------------------------------
  // Both of these are guarded by row-level security, not by the caller. A
  // session that is not in `admins` gets an empty list from the database
  // however it asks, so hiding the page is presentation, never protection.

  async function isAdmin() {
    const c = sb(), u = await user();
    if (!c || !u) return false;
    try {
      // Keyed on email, not id: a `users` row only exists after a first
      // sign-in, so an id would exclude a teammate who has not signed in yet.
      const data = checked(await c.from("admins").select("email").limit(1));
      return Boolean(data && data.length);
    } catch (error) {
      console.warn("could not check admin membership:", error);
      return false;                             // refuse rather than assume yes
    }
  }

  // Newest first, with the filer's name resolved through the foreign key.
  // Returns null on failure so the page can say the list did not load, which
  // an empty array cannot express - the queue is empty far more often.
  async function listReports() {
    const c = sb(), u = await user();
    if (!c || !u) return null;
    try {
      const data = checked(await c.from("reports")
        .select("id,kind,email_ref,title,detail,rating,context,created_at,users(email,display_name)")
        .order("created_at", { ascending: false })
        .limit(REPORT_LIMIT));
      return data || [];
    } catch (error) {
      console.warn("could not load the reports queue:", error);
      return null;
    }
  }

  // Called once after sign-in: bring this device up to date with the account.
  // Local wins on conflict, because the local mark is the one the person just
  // made and can see on screen.
  async function pull(localMarks) {
    const c = sb(), u = await user();
    if (!c || !u) return null;
    try {
      const data = checked(await c.from("reviews").select("email_ref,mark").eq("user_id", u.id));
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

  // Sign in with Google through Supabase. The Google client ID and secret live in
  // the Supabase dashboard (Auth > Providers > Google), never in this file, so the
  // code is the same before and after Google is switched on there.
  async function signIn() {
    const c = sb();
    if (!c) return false;
    try {
      const { error } = await c.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: location.origin + location.pathname,  // back to this page
          // Read the inbox, and send the replies a person presses Send on. Neither
          // can delete or change mail. Both must also be on the Google consent screen.
          scopes: "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
        },
      });
      if (error) throw error;
      return true;
    } catch (error) {
      console.warn("sign-in did not start:", error);
      return false;
    }
  }

  async function signOut() {
    const c = sb();
    if (!c) return;
    try { sessionStorage.removeItem(TOKEN_KEY); } catch (_) { /* nothing kept */ }
    googleAccess = null;
    try {
      await c.auth.signOut();
    } catch (error) {
      console.warn("sign-out failed:", error);
    }
  }

  // Calls back with the signed-in user (or null) now, and again on every sign-in
  // and sign-out. Returns false when sign-in is not available here: unconfigured,
  // or the library never arrived (offline), so the page shows no button.
  function onUser(callback) {
    const c = sb();
    if (!c) return false;
    c.auth.onAuthStateChange(function (event, session) {
      // Google's token arrives with the session right after sign-in. Supabase drops
      // it at its next refresh, so the last one seen is kept, for this tab only.
      if (!session) keepToken(null);
      else if (session.provider_token) keepToken(session.provider_token);
      callback(session ? session.user : null, event);
    });
    return true;
  }

  // The Google access token for /mailbox and /reply, or null. It lasts about an
  // hour; after that the backend answers 401 and the page asks to reconnect Gmail.
  // Kept in sessionStorage so a reload does not lose it: the tab only, gone when the
  // tab closes, never localStorage, and dropped a little before Google's hour is up.
  const TOKEN_KEY = "blockeris.gmail";
  const TOKEN_MS = 55 * 60 * 1000;
  let googleAccess = null;
  function keepToken(token) {
    googleAccess = token;
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, JSON.stringify({ token: token, until: Date.now() + TOKEN_MS }));
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch (_) { /* private mode: memory only, as before */ }
  }
  function googleToken() {
    if (googleAccess) return googleAccess;
    try {
      const kept = JSON.parse(sessionStorage.getItem(TOKEN_KEY) || "null");
      if (kept && kept.until > Date.now()) return (googleAccess = kept.token);
      sessionStorage.removeItem(TOKEN_KEY);
    } catch (_) { /* nothing kept */ }
    return null;
  }


  // Why a sign-in did not finish.
  //
  // Google hands its refusal back through Supabase as query or fragment
  // parameters on the return URL, and nothing was reading them: the page
  // simply reappeared signed out, with the reason sitting in the address bar.
  // The commonest one is an account that is not on the OAuth consent screen's
  // test-user list, which Google rejects AFTER the account chooser - so from
  // the outside it looks like the button did nothing.
  const ACCESS_DENIED = "access_denied";

  function authError() {
    const search = new URLSearchParams(location.search);
    const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    const code = search.get("error") || hash.get("error");
    if (!code) return null;

    const detail = search.get("error_description") || hash.get("error_description") || "";
    // Read once. Leaving it in the address bar means a reload shows it again,
    // and a shared link carries someone else's failure.
    history.replaceState(null, "", location.pathname);

    return { code: code, detail: detail.replace(/\+/g, " ") };
  }

  window.Store = { pushMark, pushReply, pushReport, pushCorrection, pull, signIn, signOut, onUser, authError, googleToken,
                   isAdmin, listReports, currentUser: user,
                   ACCESS_DENIED, MARK_OK, MARK_BACK };
})();
