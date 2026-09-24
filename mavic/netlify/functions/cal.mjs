// Los Primos: shared calendar storage.
// GET  /api/cal          -> whole calendar document
// POST /api/cal {op,...} -> apply one change, return the updated document
// If the FAMILY_CODE env var is set, every request needs a matching x-family-code header.

import { getStore } from "@netlify/blobs";
import { createHash, timingSafeEqual } from "node:crypto";

export const config = { path: "/api/cal" };

const KEY = "calendar";
const ID_RE = /^[a-z0-9-]{1,24}$/;
// Keep in sync with FAMILY.members in public/index.html. Anyone else is refused.
const MEMBER_IDS = new Set(["gabriel", "mariana", "david", "quique", "patty", "adriana", "oscar", "kristian", "nacho", "ricky"]);
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
const MMDD_RE = /^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const validMMDD = (s) => {
  if (!MMDD_RE.test(s)) return false;
  const [m, d] = s.split("-").map(Number);
  return new Date(2000, m - 1, d).getMonth() === m - 1; // 2000 is a leap year, so 02-29 is allowed
};
const STATUSES = ["in", "maybe", "out"];
const TZ_RE = /^[A-Za-z]+(?:\/[A-Za-z0-9_+-]+){1,2}$/;
const LOG_MAX = 100;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clip = (v, n) => String(v ?? "").trim().slice(0, n);

export const emptyDoc = () => ({ v: 1, rev: 0, marks: {}, plans: {}, profiles: {}, log: [] });

function readCode() {
  const fromNetlify = globalThis.Netlify?.env?.get?.("FAMILY_CODE");
  return (fromNetlify ?? process.env.FAMILY_CODE ?? "").trim();
}

const norm = (s) => createHash("sha256").update(String(s).trim().toLowerCase()).digest();

function codeMatches(given, wanted) {
  return timingSafeEqual(norm(given), norm(wanted));
}

function addLog(doc, entry) {
  const now = Date.now();
  const last = doc.log[0];
  // Collapse rapid toggles on the same day by the same person into one entry.
  // Only quick taps on the same day collapse; plan changes and removals always keep their own line.
  if (entry.kind === "mark" && last && last.kind === "mark" && last.who === entry.who && last.date === entry.date && now - last.t < 90_000) {
    doc.log[0] = { ...entry, t: now };
  } else {
    doc.log.unshift({ ...entry, t: now });
  }
  doc.log.length = Math.min(doc.log.length, LOG_MAX);
}

// Pure function: mutates doc, returns an error string or null.
export function applyOp(doc, op) {
  if (!op || typeof op !== "object") return "bad-request";
  const who = op.who;
  if (!ID_RE.test(String(who)) || !MEMBER_IDS.has(who)) return "bad-member";

  switch (op.op) {
    case "mark": {
      if (!DAY_RE.test(String(op.date))) return "bad-date";
      const status = op.status ?? null;
      if (status !== null && !STATUSES.includes(status)) return "bad-status";
      const day = doc.marks[op.date] || {};
      if (status === null) delete day[who];
      else day[who] = status;
      if (Object.keys(day).length) doc.marks[op.date] = day;
      else delete doc.marks[op.date];
      addLog(doc, { who, kind: "mark", date: op.date, status: status || "clear" });
      return null;
    }
    case "marks": {
      // Several dates in one save: { set: { "2026-10-10": "in", "2026-10-11": null, ... } }
      const entries = Object.entries(op.set || {});
      if (!entries.length || entries.length > 62) return "bad-set";
      for (const [date, status] of entries) {
        if (!DAY_RE.test(date)) return "bad-date";
        if (status !== null && !STATUSES.includes(status)) return "bad-status";
      }
      for (const [date, status] of entries) {
        const day = doc.marks[date] || {};
        if (status === null) delete day[who];
        else day[who] = status;
        if (Object.keys(day).length) doc.marks[date] = day;
        else delete doc.marks[date];
      }
      const dates = entries.map((e) => e[0]).sort();
      addLog(doc, { who, kind: "marks", date: dates[0], to: dates[dates.length - 1], count: dates.length, status: entries[0][1] || "clear" });
      return null;
    }
    case "plan": {
      if (!DAY_RE.test(String(op.date))) return "bad-date";
      // "base" is the plan version the editor started from; if someone saved in between, refuse.
      if ("base" in op && (op.base ?? null) !== (doc.plans[op.date]?.updatedAt ?? null)) return "conflict";
      if (op.plan === null) {
        if (!doc.plans[op.date]) return null;
        if (doc.plans[op.date].locked) return "locked";
        const old = doc.plans[op.date];
        delete doc.plans[op.date];
        addLog(doc, { who, kind: "unplan", date: op.date, title: old.title });
        return null;
      }
      const title = clip(op.plan?.title, 60);
      if (!title) return "missing-title";
      const prev = doc.plans[op.date];
      const time = clip(op.plan.time, 30);
      const tz = clip(op.plan.tz, 40);
      const safeTz = TZ_RE.test(tz) ? tz : "";
      const place = clip(op.plan.place, 60);
      // Editing what, when or where of a confirmed plan un-confirms it so everyone re-checks.
      const material = !!prev && (prev.title !== title || (prev.time || "") !== time || (prev.tz || "") !== (time ? safeTz : "") || (prev.place || "") !== place);
      const keepLock = !!prev?.locked && !material;
      doc.plans[op.date] = {
        title,
        time,
        tz: time ? safeTz : "",
        place,
        note: clip(op.plan.note, 240),
        by: prev?.by || who,
        locked: keepLock,
        lockedBy: keepLock ? prev.lockedBy : null,
        changed: !!((prev?.locked && material) || (prev?.changed && !keepLock)),
        updatedAt: Date.now(),
      };
      addLog(doc, { who, kind: prev ? "replan" : "plan", date: op.date, title });
      return null;
    }
    case "lock": {
      if (!DAY_RE.test(String(op.date))) return "bad-date";
      const plan = doc.plans[op.date];
      if (!plan) return "no-plan";
      plan.locked = !!op.locked;
      plan.lockedBy = plan.locked ? who : null;
      plan.changed = false;
      addLog(doc, { who, kind: plan.locked ? "lock" : "unlock", date: op.date, title: plan.title });
      return null;
    }
    case "profile": {
      const bday = op.birthday ? String(op.birthday) : "";
      if (bday && !validMMDD(bday)) return "bad-birthday";
      const p = doc.profiles[who] || {};
      if (bday) p.birthday = bday;
      else delete p.birthday;
      if (Object.keys(p).length) doc.profiles[who] = p;
      else delete doc.profiles[who];
      addLog(doc, { who, kind: "bday", date: "", status: bday ? "set" : "clear" });
      return null;
    }
    default:
      return "bad-op";
  }
}

// Test seam: local tests inject a fake store; Netlify uses Blobs.
const storeFor = () => globalThis.__primosStore ?? getStore({ name: "los-primos", consistency: "strong" });

export default async (req) => {
  // FAMILY_CODE is optional. Not set: the link alone opens the calendar.
  // Set it in Netlify later and every phone asks for it (or uses the #code= link).
  const wanted = readCode();
  if (wanted) {
    const given = req.headers.get("x-family-code") || "";
    if (!given || !codeMatches(given, wanted)) {
      return json({ error: given ? "bad-code" : "need-code" }, 401);
    }
  }

  const store = storeFor();

  if (req.method === "GET") {
    const doc = (await store.get(KEY, { type: "json" })) || emptyDoc();
    return json(doc);
  }

  if (req.method !== "POST") return json({ error: "method" }, 405);

  let op;
  try {
    op = await req.json();
  } catch {
    return json({ error: "bad-json" }, 400);
  }

  // Optimistic concurrency: retry if someone else wrote in between.
  for (let attempt = 0; attempt < 6; attempt++) {
    const current = await store.getWithMetadata(KEY, { type: "json" });
    const doc = current?.data || emptyDoc();
    const err = applyOp(doc, op);
    if (err) return json({ error: err }, 400);
    doc.rev = (doc.rev || 0) + 1;
    doc.updatedAt = Date.now();
    const res = current
      ? await store.setJSON(KEY, doc, { onlyIfMatch: current.etag })
      : await store.setJSON(KEY, doc, { onlyIfNew: true });
    if (res.modified) return json(doc);
    await sleep(40 + Math.random() * 160);
  }
  return json({ error: "busy" }, 409);
};
