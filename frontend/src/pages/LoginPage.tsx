import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "@/lib/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      navigate("/dashboard", { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao autenticar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#060d14]">
      <div className="w-full max-w-sm space-y-6 px-6">
        <div className="text-center space-y-1">
          <p className="text-[#00ff88] font-mono text-xs tracking-widest uppercase">AlphaCota</p>
          <h1 className="text-white font-semibold text-xl">Acesso restrito</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-[#8899aa] text-xs font-mono uppercase tracking-wider">
              Usuário / E-mail
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="w-full bg-[#0d1820] border border-[#1e3040] rounded px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-[#00ff88] transition-colors"
            />
          </div>

          <div className="space-y-1">
            <label className="text-[#8899aa] text-xs font-mono uppercase tracking-wider">
              Senha
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full bg-[#0d1820] border border-[#1e3040] rounded px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-[#00ff88] transition-colors"
            />
          </div>

          {error && (
            <p className="text-[#ff4444] font-mono text-xs">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#00ff88] text-[#060d14] font-mono font-bold text-sm py-2 rounded hover:bg-[#00cc6e] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Autenticando..." : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
