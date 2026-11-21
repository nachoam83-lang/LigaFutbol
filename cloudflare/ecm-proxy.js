// Worker "ecm-probe" (ecm-proxy): hace DOS trabajos gratis desde Cloudflare.
//
// 1) fetch  -> proxy a juegosdeportivos.ecmadrid.org con IP de España (Placement fijado en España).
//    Uso: GET /?u=<URL-codificada de ECM>  con cabecera  X-Key: <KEY>
//
// 2) scheduled -> Cron Triggers (hora UTC):
//    · "*/20 6-20 * * SAT,SUN"   lanza el workflow de extracción (fin de semana, cada 20 min)
//    · "7 6-20/2 * * MON-FRI"    lanza el workflow de extracción (entre semana, cada 2 h)
//
// 3) Avisos push: rutas /push/* que guardan las suscripciones de los móviles en un KV PRIVADO (binding "SUBS").
//    · POST /push/sub    (desde la app)   guarda/renueva una suscripción y los equipos que sigue
//    · POST /push/unsub  (desde la app)   la borra
//    · GET  /push/subs   (X-Key)          lista todas (lo usa el workflow que envía los avisos)
//    · POST /push/del    (X-Key)          borra suscripciones caducadas
//
// Variables y secretos del Worker (Settings > Variables and Secrets):
//    KEY         (secret)  clave del proxy
//    GH_TOKEN    (secret)  token fino de GitHub con permiso "Actions: Read and write" SOLO sobre el repo
//    GH_REPO     (texto)   nachoam83-lang/LigaFutbol
const HOST = "juegosdeportivos.ecmadrid.org";
const WORKFLOW = "extractor.yml";
const ORIGENES = ["https://ligapsj.onrender.com", "http://localhost:8000"];
const TTL_SUB = 60 * 24 * 3600; // 60 días; la app la renueva cada vez que se abre

function cors(request) {
  const o = request.headers.get("Origin") || "";
  const h = { "Vary": "Origin", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type" };
  if (ORIGENES.includes(o.toLowerCase())) h["Access-Control-Allow-Origin"] = o;
  return h;
}
function json(obj, status, extra) {
  return new Response(JSON.stringify(obj), { status: status || 200, headers: { "content-type": "application/json", ...(extra || {}) } });
}
async function idDe(endpoint) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function subValida(sub) {
  return sub && typeof sub.endpoint === "string" && sub.endpoint.startsWith("https://") && sub.endpoint.length < 800 &&
    sub.keys && typeof sub.keys.p256dh === "string" && typeof sub.keys.auth === "string" &&
    sub.keys.p256dh.length < 200 && sub.keys.auth.length < 100;
}
function equiposValidos(eqs) {
  if (!Array.isArray(eqs) || eqs.length > 12) return null;
  const out = [];
  for (const e of eqs) {
    if (!e || typeof e !== "object") return null;
    const t = (v) => String(v == null ? "" : v).slice(0, 80);
    out.push({ d: t(e.d), c: t(e.c), k: t(e.k), g: t(e.g), n: t(e.n) });
  }
  return out;
}
async function rutaPush(request, env, url) {
  const c = cors(request);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: c });
  if (!env.SUBS) return json({ error: "falta el binding SUBS" }, 500, c);
  const admin = env.KEY && request.headers.get("X-Key") === env.KEY;

  if (url.pathname === "/push/sub" && request.method === "POST") {
    let b; try { b = await request.json(); } catch { return json({ error: "json" }, 400, c); }
    const eqs = equiposValidos(b.equipos);
    if (!subValida(b.sub) || !eqs) return json({ error: "datos no válidos" }, 400, c);
    const id = await idDe(b.sub.endpoint);
    await env.SUBS.put(id, JSON.stringify({ sub: { endpoint: b.sub.endpoint, keys: b.sub.keys }, equipos: eqs, ts: Date.now() }), { expirationTtl: TTL_SUB });
    return json({ ok: true }, 200, c);
  }
  if (url.pathname === "/push/unsub" && request.method === "POST") {
    let b; try { b = await request.json(); } catch { return json({ error: "json" }, 400, c); }
    if (!b || typeof b.endpoint !== "string") return json({ error: "datos no válidos" }, 400, c);
    await env.SUBS.delete(await idDe(b.endpoint));
    return json({ ok: true }, 200, c);
  }
  if (url.pathname === "/push/subs" && request.method === "GET") {
    if (!admin) return new Response("forbidden", { status: 403 });
    const out = []; let cursor;
    do {
      const l = await env.SUBS.list({ cursor });
      for (const k of l.keys) { const v = await env.SUBS.get(k.name); if (v) out.push({ id: k.name, ...JSON.parse(v) }); }
      cursor = l.list_complete ? undefined : l.cursor;
    } while (cursor);
    return json(out);
  }
  if (url.pathname === "/push/del" && request.method === "POST") {
    if (!admin) return new Response("forbidden", { status: 403 });
    let b; try { b = await request.json(); } catch { return json({ error: "json" }, 400); }
    for (const id of (b.ids || []).slice(0, 200)) await env.SUBS.delete(String(id));
    return json({ ok: true });
  }
  return new Response("not found", { status: 404, headers: c });
}

async function lanzarWorkflow(env) {
  if (!env.GH_TOKEN || !env.GH_REPO) { console.log("Faltan GH_TOKEN o GH_REPO"); return; }
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ligafutbol-cron",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  console.log("dispatch GitHub:", r.status, r.status === 204 ? "ok" : await r.text());
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(lanzarWorkflow(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/push/")) return rutaPush(request, env, url);
    if (!env.KEY || request.headers.get("X-Key") !== env.KEY) {
      return new Response("forbidden", { status: 403 });
    }
    let destino;
    try { destino = new URL(url.searchParams.get("u") || ""); } catch { return new Response("bad url", { status: 400 }); }
    if (destino.protocol !== "https:" || destino.hostname !== HOST) {
      return new Response("host no permitido", { status: 400 });
    }
    const r = await fetch(destino.toString(), {
      headers: {
        "User-Agent": "Mozilla/5.0",
        "Accept": request.headers.get("Accept") || "*/*",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    return new Response(r.body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") || "application/octet-stream" },
    });
  },
};
