import { useState } from "react";
import "./App.css";

const SHORTENER_URL = import.meta.env.VITE_SHORTENER_URL || "http://localhost:9000";
const ANALYTICS_URL = import.meta.env.VITE_ANALYTICS_URL || "http://localhost:9001";
export default function App() {
  const [url, setUrl]         = useState("");
  const [result, setResult]   = useState(null);
  const [stats, setStats]     = useState(null);
  const [allStats, setAllStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const [tab, setTab]         = useState("shorten");

  async function shorten() {
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`${SHORTENER_URL}/shorten`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "Erreur serveur");
      }
      const data = await res.json();
      setResult(data);
      // Fetch stats immediately
      fetchStats(data.short_code);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function fetchStats(code) {
    try {
      const res = await fetch(`${ANALYTICS_URL}/stats/${code}`);
      const data = await res.json();
      setStats(data);
    } catch (e) {
      console.error(e);
    }
  }

  async function fetchAllStats() {
    setLoading(true);
    setError("");
    try {
      // Récupère toutes les URLs créées depuis le shortener
      const resUrls = await fetch(`${SHORTENER_URL}/urls`);
      if (!resUrls.ok) throw new Error("Impossible de charger les URLs");
      const urls = await resUrls.json();

      // Récupère les stats de clics depuis analytics (best-effort)
      let clickMap = {};
      try {
        const resStats = await fetch(`${ANALYTICS_URL}/stats`);
        if (resStats.ok) {
          const stats = await resStats.json();
          stats.forEach((s) => { clickMap[s.short_code] = s.click_count; });
        }
      } catch (_) {}

      // Merge : toutes les URLs avec leur nombre de clics (0 si jamais cliquée)
      setAllStats(urls.map((u) => ({
        short_code:  u.short_code,
        original_url: u.original_url,
        short_url:   u.short_url,
        click_count: clickMap[u.short_code] ?? 0,
        created_at:  u.created_at,
      })));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function copyToClipboard(text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
    } else {
      const el = document.createElement("textarea");
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
  }

  return (
    <div className="app">
      <header>
        <div className="logo">⚡ URLShort</div>
        <p className="subtitle">Raccourcisseur d'URL — microservices FastAPI + Kubernetes</p>
      </header>

      <nav className="tabs">
        <button className={tab === "shorten" ? "active" : ""} onClick={() => setTab("shorten")}>
          Raccourcir
        </button>
        <button
          className={tab === "dashboard" ? "active" : ""}
          onClick={() => { setTab("dashboard"); fetchAllStats(); }}
        >
          Dashboard
        </button>
      </nav>

      {tab === "shorten" && (
        <main className="panel">
          <div className="input-row">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/une-url-tres-longue"
              onKeyDown={(e) => e.key === "Enter" && shorten()}
            />
            <button onClick={shorten} disabled={loading}>
              {loading ? "…" : "Raccourcir"}
            </button>
          </div>

          {error && <div className="error">{error}</div>}

          {result && (
            <div className="result-card">
              <div className="result-header">URL raccourcie ✓</div>
              <div className="short-url-row">
                <a href={result.short_url} target="_blank" rel="noreferrer">
                  {result.short_url}
                </a>
                <button className="copy-btn" onClick={() => copyToClipboard(result.short_url)}>
                  Copier
                </button>
              </div>
              <div className="original">↳ {result.original_url}</div>

              {stats && (
                <div className="stats-inline">
                  <span>👁 {stats.click_count} clic{stats.click_count !== 1 ? "s" : ""}</span>
                  <button className="refresh-btn" onClick={() => fetchStats(result.short_code)}>
                    Rafraîchir
                  </button>
                </div>
              )}
            </div>
          )}
        </main>
      )}

      {tab === "dashboard" && (
        <main className="panel">
          <div className="dashboard-header">
            <h2>Toutes les URLs</h2>
            <button onClick={fetchAllStats} disabled={loading}>
              {loading ? "…" : "↻ Rafraîchir"}
            </button>
          </div>

          {allStats.length === 0 && !loading && (
            <div className="empty">Aucune URL raccourcie pour l'instant.</div>
          )}

          <table className="stats-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Clics</th>
                <th>Créé le</th>
              </tr>
            </thead>
            <tbody>
              {allStats.map((s) => (
                <tr key={s.short_code}>
                  <td>
                    <a
                      href="#"
                      onClick={(e) => { e.preventDefault(); setTab("shorten"); fetchStats(s.short_code); setResult({ short_code: s.short_code, short_url: `${SHORTENER_URL}/${s.short_code}`, original_url: "—" }); }}
                    >
                      {s.short_code}
                    </a>
                  </td>
                  <td>{s.click_count}</td>
                  <td>{new Date(s.created_at).toLocaleDateString("fr-FR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </main>
      )}

      <footer>
        Projet M1 — FastAPI · gRPC · Docker · Kubernetes · Istio
      </footer>
    </div>
  );
}
