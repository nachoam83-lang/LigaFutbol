// Worker "ecm-proxy": reenvía peticiones GET a juegosdeportivos.ecmadrid.org desde una IP de España.
// Requiere: Placement fijado a una región de España y la variable secreta KEY (Settings > Variables and Secrets).
// Uso: GET /?u=<URL-codificada de ECM>   con cabecera  X-Key: <KEY>
const HOST = "juegosdeportivos.ecmadrid.org";

export default {
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
