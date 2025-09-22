'use client';

import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search, PauseCircle, TrendingUp, FileText, Sparkles, Zap, Layers } from 'lucide-react';

function useApi() {
  const base = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
  const api = useMemo(() => axios.create({ baseURL: base, timeout: 30000, headers: { 'Content-Type': 'application/json' } }), [base]);
  return { api, base };
}

export default function Dashboard() {
  const { api, base } = useApi();
  const [dashboard, setDashboard] = useState<any>(null);
  const [systemLogs, setSystemLogs] = useState<any[]>([]);
  const [processing, setProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview'|'logs'>('overview');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function safe<T>(fn: () => Promise<T>) {
    try { setErrMsg(null); return await fn(); } catch (e: any) {
      const status = e?.response?.status; const data = e?.response?.data;
      setErrMsg(`Request failed (${status || 'network'}): ${typeof data === 'string' ? data : JSON.stringify(data)}`);
      throw e;
    }
  }

  const fetchDashboard = async () => { const res = await safe(() => api.get('/api/dashboard')); setDashboard(res.data); };
  const fetchSystemLogs = async () => { const res = await safe(() => api.get('/api/system-logs')); setSystemLogs(res.data.logs || []); };

  useEffect(() => {
    (async () => { await Promise.allSettled([fetchDashboard(), fetchSystemLogs()]); })();
    const id = setInterval(() => { fetchDashboard(); if (activeTab === 'logs') fetchSystemLogs(); }, 7000);
    return () => clearInterval(id);
  }, [activeTab]);

  const handle = async (fn: () => Promise<any>) => {
    if (processing) return; setProcessing(true);
    try { await safe(fn); } finally { setTimeout(() => { fetchDashboard(); fetchSystemLogs(); setProcessing(false); }, 1500); }
  };

  const scanAll = () => handle(() => api.post('/api/scan'));
  const processQueue = () => handle(() => api.post('/api/process-queue'));
  const togglePause = () => handle(() => api.post('/api/pause'));
  const testConnection = async () => { await safe(() => api.get('/api/health')); alert(`✅ Frontend can reach backend:\n${base}`); };

  if (!dashboard) {
    return (<div className="min-h-screen bg-gray-50 flex items-center justify-center"><div className="text-center"><Activity className="w-12 h-12 text-gray-400 animate-pulse mx-auto mb-4" /><p className="text-gray-500">Connecting to agent...</p><p className="text-xs text-gray-400 mt-2">API: {base}</p></div></div>);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4"><div className="flex justify-between items-center"><div className="flex items-center space-x-3"><div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl"><Sparkles className="w-6 h-6 text-white" /></div><div><h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">AI SEO Content Agent</h1><p className="text-xs text-gray-600">API: {base}</p></div></div><div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} shadow-lg`}><div className="flex items-center space-x-2">{dashboard.system.is_paused ? (<><div className="w-2 h-2 bg-red-500 rounded-full"></div><span>PAUSED</span></>) : (<><div className="w-2 h-2 bg-green-500 rounded-full relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping"></div><span>ACTIVE</span></>)}</div></div></div></div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6"><div className="flex space-x-1 p-1 bg-white/50 backdrop-blur-sm rounded-2xl shadow-inner">{['overview', 'logs'].map((tab) => (<button key={tab} onClick={() => setActiveTab(tab)} className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${activeTab === tab ? 'bg-white text-purple-600 shadow-lg' : 'text-gray-600 hover:text-gray-900'}`}>{tab.charAt(0).toUpperCase() + tab.slice(1)}</button>))}</div></div>
      
      <main className="max-w-7xl mx-auto px-6 pb-12 space-y-6">
        {errMsg && <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">{errMsg}</div>}
        {activeTab === 'overview' && (
            <>
            <div className="flex flex-wrap gap-3">
                <Btn onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search className="w-4 h-4" />} label="Scan All" gradient="from-blue-500 to-cyan-500" />
                <Btn onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap className="w-4 h-4" />} label="Process Queue" gradient="from-green-500 to-emerald-500" />
                <Btn onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />} label={dashboard.system.is_paused ? "Resume" : "Pause"} gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"} />
                <Btn onClick={testConnection} icon={<RefreshCw className="w-4 h-4" />} label="Test Connection" gradient="from-gray-500 to-gray-600" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Stat title="Products" stats={dashboard.stats.products} icon={<Package className="w-5 h-5" />} />
                <Stat title="Collections" stats={dashboard.stats.collections} icon={<Layers className="w-5 h-5" />} />
                <Stat title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} />
                <Stat title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'} icon={<Clock className="w-5 h-5" />} />
            </div>
            </>
        )}
        {activeTab === 'logs' && (
            <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden">
                <div className="px-6 py-4 bg-gradient-to-r from-purple-500 to-pink-500"><h2 className="text-lg font-semibold text-white">System Logs</h2></div>
                <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto font-mono text-xs">
                    {systemLogs.length === 0 ? <div className="p-8 text-center text-gray-500">No logs yet.</div> : 
                    systemLogs.map((log: any, i: number) => (
                        <div key={i} className={`p-3 flex items-start space-x-3 ${log.status === 'error' ? 'bg-red-50' : ''}`}>
                            <span className="text-gray-400">{new Date(log.timestamp).toLocaleTimeString()}</span>
                            <span className={`font-bold ${log.service === 'shopify' ? 'text-green-600' : log.service === 'openai' ? 'text-purple-600' : 'text-blue-600'}`}>{log.service.toUpperCase()}</span>
                            <span className="flex-1 text-gray-700">{log.message}</span>
                        </div>
                    ))}
                </div>
            </div>
        )}
      </main>
    </div>
  );
}

// --- Self-Contained Components ---
function Btn({ onClick, disabled, icon, label, gradient }: any) { return (<button onClick={onClick} disabled={disabled} className={`px-5 py-2 bg-gradient-to-r ${gradient} text-white rounded-lg font-semibold shadow hover:shadow-lg transition-all disabled:opacity-50 flex items-center space-x-2`}>{icon}<span>{label}</span></button>); }
function Stat({ title, stats, value, icon }: any) { const total=stats?.total??value??0; const completed=stats?.completed??0; const pending=stats?.pending??0; return (<div className="bg-white rounded-lg shadow p-5"><div className="flex items-center justify-between"><div><p className="text-sm text-gray-600">{title}</p><p className="text-3xl font-bold mt-1">{total}</p>{stats&&<div className="flex gap-4 text-xs text-gray-500 mt-1"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div>}</div><div className="text-gray-400">{icon}</div></div></div>); }
