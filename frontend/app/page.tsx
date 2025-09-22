'use client';

import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search,
  PauseCircle, TrendingUp, FileText, Plus, Layers, Sparkles, Zap, Edit3
} from 'lucide-react';

function useApi() {
  const base = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
  const api = useMemo(() => axios.create({ baseURL: base, timeout: 30000, headers: { 'Content-Type': 'application/json' } }), [base]);
  return { api, base };
}

export default function Dashboard() {
  const { api, base } = useApi();
  const [dashboard, setDashboard] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [processing, setProcessing] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function safe<T>(fn: () => Promise<T>) {
    try {
      setErrMsg(null);
      return await fn();
    } catch (e: any) {
      console.error('API error:', e?.response?.status, e?.response?.data || e?.message);
      const status = e?.response?.status;
      const data = e?.response?.data;
      setErrMsg(`Request failed (${status || 'network'}): ${typeof data === 'string' ? data : JSON.stringify(data)}`);
      throw e;
    }
  }

  const fetchDashboard = async () => {
    const res = await safe(() => api.get('/api/dashboard'));
    setDashboard(res.data);
  };
  const fetchLogs = async () => {
    const res = await safe(() => api.get('/api/logs'));
    setLogs(res.data.logs || []);
  };

  useEffect(() => {
    (async () => {
      await Promise.allSettled([fetchDashboard(), fetchLogs()]);
    })();
    const id = setInterval(() => { fetchDashboard(); fetchLogs(); }, 10000);
    return () => clearInterval(id);
  }, []);

  const handle = async (fn: () => Promise<any>) => {
    if (processing) return;
    setProcessing(true);
    try { await safe(fn); } finally { setTimeout(() => { fetchDashboard(); fetchLogs(); setProcessing(false); }, 1200); }
  };

  const scanAll = () => handle(() => api.post('/api/scan'));
  const processQueue = () => handle(() => api.post('/api/process-queue'));
  const togglePause = () => handle(() => api.post('/api/pause'));
  const testConnection = async () => { await safe(() => api.get('/api/health')); alert(`✅ Frontend can reach backend:\n${base}`); };

  if (!dashboard) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-12 h-12 text-gray-400 animate-pulse mx-auto mb-4" />
          <p className="text-gray-500">Loading dashboard...</p>
          <p className="text-xs text-gray-400 mt-2">API: {base}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
                  AI SEO Content Agent
                </h1>
                <p className="text-xs text-gray-600">API: {base}</p>
              </div>
            </div>
            <div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} shadow-lg`}>
              <div className="flex items-center space-x-2">
                {dashboard.system.is_paused ? (
                  <>
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                    <span>PAUSED</span>
                  </>
                ) : (
                  <>
                    <div className="w-2 h-2 bg-green-500 rounded-full relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping"></div>
                    <span>ACTIVE</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {errMsg && <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">{errMsg}</div>}

        <div className="flex flex-wrap gap-3">
          <Btn onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search className="w-4 h-4" />} label="Scan All" />
          <Btn onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap className="w-4 h-4" />} label="Process Queue" />
          <Btn onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />} label={dashboard.system.is_paused ? "Resume" : "Pause"} />
          <Btn onClick={testConnection} icon={<RefreshCw className="w-4 h-4" />} label="Test Connection" gray />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Stat title="Products" stats={dashboard.stats.products} icon={<Package className="w-5 h-5" />} />
          <Stat title="Collections" stats={dashboard.stats.collections} icon={<Layers className="w-5 h-5" />} />
          <Stat title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} />
          <Stat title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'} icon={<Clock className="w-5 h-5" />} />
        </div>

        <div className="bg-white rounded-lg shadow-md">
          <h2 className="text-lg font-semibold p-4 border-b">Recent Activity</h2>
          <div className="divide-y max-h-96 overflow-y-auto">
            {!dashboard.recent_activity || dashboard.recent_activity.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                <Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p>No activity yet</p>
              </div>
            ) : (
              dashboard.recent_activity.map((item: any) => (
                <div key={`${item.type}-${item.id}`} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center space-x-2">
                    {item.type === 'collection' ? <Layers className="w-4 h-4 text-purple-500" /> : <Package className="w-4 h-4 text-blue-500" />}
                    <h3 className="font-medium text-gray-900">{item.title}</h3>
                    <span className="ml-auto text-xs text-gray-500">{item.status}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">ID: {item.id}{item.updated ? ` • ${new Date(item.updated).toLocaleString()}` : ''}</div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-md">
          <h2 className="text-lg font-semibold p-4 border-b">Generation Logs</h2>
          <div className="divide-y max-h-[500px] overflow-y-auto">
            {!logs || logs.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                <FileText className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p>No content generated yet</p>
              </div>
            ) : (
              logs.map((log: any, i: number) => (
                <div key={i} className="p-4">
                  <div className="font-medium text-gray-900">{log.item_title}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    SEO Title: {log.seo_title || '—'} • Meta: {log.meta_description ? `${log.meta_description.length} chars` : '—'} • {new Date(log.generated_at).toLocaleString()}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function Btn({ onClick, disabled, icon, label, gray }: any) {
  const classes = gray ? 'from-gray-500 to-gray-600' : 'from-purple-600 to-pink-600';
  return (
    <button onClick={onClick} disabled={disabled} className={`px-5 py-2 bg-gradient-to-r ${classes} text-white rounded-lg font-semibold shadow hover:shadow-lg transition-all disabled:opacity-50 flex items-center space-x-2`}>
      {icon}<span>{label}</span>
    </button>
  );
}

function Stat({ title, stats, value, icon }: any) {
  const total = stats?.total ?? value ?? 0;
  const completed = stats?.completed ?? 0;
  const pending = stats?.pending ?? 0;
  return (
    <div className="bg-white rounded-lg shadow p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{title}</p>
          <p className="text-3xl font-bold mt-1">{total}</p>
          {stats && <div className="flex gap-4 text-xs text-gray-500 mt-1"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div>}
        </div>
        <div className="text-gray-400">{icon}</div>
      </div>
    </div>
  );
}
