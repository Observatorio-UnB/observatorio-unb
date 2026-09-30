// Busca semântica do painel publicado: transforma a consulta em embedding e chama
// public.observatorio_buscar (db/migrations/0018_api_publica_supabase.sql).
//
// O modelo é o gte-small do próprio Supabase (384 dimensões, mesmo espaço vetorial que
// src/busca/vetorizar.py grava em busca.documentos).
//
// Deploy: supabase functions deploy buscar --project-ref <ref>
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const modelo = new Supabase.ai.Session("gte-small");
const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!);

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const resposta = (corpo: unknown, status = 200) =>
  new Response(JSON.stringify(corpo), { status, headers: { ...CORS, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  if (req.method !== "POST") return resposta({ erro: "Use POST." }, 405);

  let corpo: { consulta?: unknown; tipo?: unknown; k?: unknown };
  try {
    corpo = await req.json();
  } catch {
    return resposta({ erro: "Corpo não é JSON." }, 400);
  }
  const consulta = typeof corpo.consulta === "string" ? corpo.consulta.trim() : "";
  if (!consulta || consulta.length > 500) return resposta({ erro: "consulta deve ter de 1 a 500 caracteres." }, 400);

  const k = Number.isInteger(corpo.k) ? (corpo.k as number) : 8;
  const tipo = typeof corpo.tipo === "string" ? corpo.tipo : null;
  try {
    const embedding = await modelo.run(consulta, { mean_pool: true, normalize: true });
    const { data, error } = await supabase.rpc("observatorio_buscar", {
      vetor: `[${Array.from(embedding as ArrayLike<number>).join(",")}]`,
      tipo,
      k,
    });
    // tipo ou k fora do permitido viram exceção na função SQL: erro do chamador, não do servidor.
    if (error) return resposta({ erro: error.message }, error.code === "P0001" ? 400 : 500);
    return resposta(data);
  } catch (e) {
    // Sem o catch o runtime devolve um 500 sem CORS e o navegador só enxerga "NetworkError".
    console.error(e);
    return resposta({ erro: "Falha ao vetorizar a consulta." }, 503);
  }
});
