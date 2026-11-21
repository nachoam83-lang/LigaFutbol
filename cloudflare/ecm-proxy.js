// Worker "ecm-probe" (ecm-proxy): hace DOS trabajos gratis desde Cloudflare.
//
// 1) fetch  -> proxy a juegosdeportivos.ecmadrid.org con IP de España (Placement fijado en España).
//    Uso: GET /?u=<URL-codificada de ECM>  con cabecera  X-Key: <KEY>
//
// 2) scheduled -> Cron Triggers (hora UTC):
//    · "*/20 6-20 * * SAT,SUN"   lanza el workflow de extracción (fin de semana, cada 20 min)
//    · "7 6-20/2 * * MON-FRI"    lanza el workflow de extracción (entre semana, cada 2 h)
//    · "*/10 6-21 * * *"         despierta Render (evita el arranque en frío) -> necesita RENDER_URL
//
// Variables y secretos del Worker (Settings > Variables and Secrets):
//    KEY         (secret)  clave del proxy
//    GH_TOKEN    (secret)  token fino de GitHub con permiso "Actions: Read and write" SOLO sobre el repo
//    GH_REPO     (texto)   nachoam83-lang/LigaFutbol
//    RENDER_URL  (texto)   https://ligaPSJ.onrender.com   (opcional)
const HOST = "juegosdeportivos.ecmadrid.org";
const WORKFLOW = "extractor.yml";

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

async function despertarRender(env) {
  if (!env.RENDER_URL) return;
  try {
    const r = await fetch(env.RENDER_URL.replace(/\/$/, "") + "/api/datos-estado", { headers: { "User-Agent": "ligafutbol-cron" } });
    console.log("ping Render:", r.status);
  } catch (e) { console.log("ping Render error:", String(e)); }
}

export default {
  async scheduled(event, env, ctx) {
    if (event.cron.startsWith("*/10")) ctx.waitUntil(despertarRender(env));
    else ctx.waitUntil(lanzarWorkflow(env));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
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
