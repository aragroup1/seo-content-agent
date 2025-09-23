'use client';

import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search,
  PauseCircle, AlertTriangle, TrendingUp, FileText, Plus, Layers, Sparkles,
  Zap, Target, Edit3, Trash2, TestTube2
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<any>(null);
  const [processing, setProcessing] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const api = useMemo(() => axios.create({ baseURL: API_URL, timeout: 60000 }), [API_URL]);

  async function safe<T>(fn: () => Promise<T>) {
    try {
      setErrMsg(null);
      return await fn();
    } catch (e: any) {
      console.error('API error:', e?.response?.status, e?.response?.data || e?.message);
      const status = e?.response?.status;
      const data = e?.response?.data;
      const message = typeof data === 'string' ? data : (data?.detail || JSON.stringify(data));
      setErrMsg(`Request failed (${status || 'network'}): ${message}`);
      throw e;
    }
  }

  const fetchDashboard = async () => {
    try { const res = await safe(() => api.get('/api/dashboard')); if (res && res.data) setDashboard(res.data); } catch (e) {}
  };

  useEffect(() => {
    fetchDashboard();
    const id = setInterval(fetchDashboard, 10000);
    return () => clearInterval(id);
  }, []);

  const handleApiAction = async (fn: () => Promise<any>) => {
    if (processing) return;
    setProcessing(true);
    try {
      await safe(fn);
      setTimeout(() => {
        fetchDashboard();
        setProcessing(false);
      }, 2000);
    } catch {
      setProcessing(false);
    }
  };

  const scanAll = () => handleApiAction(() => api.post('/api/scan'));
  const processQueue = () => handleApiAction(() => api.post('/api/process-queue'));
  const togglePause = () => handleApiAction(() => api.post('/api/pause'));
  
  const testOpenAI = async () => {
    setProcessing(true);
    try {
        const res = await safe(() => api.post('/api/test-openai', { prompt: 'say hello world' }));
        alert(`✅ OpenAI Test SUCCESS!\n\nResponse: "${res.data.response}"`);
    } catch (e: any) {
        // Error is already handled by safe() and displayed in errMsg
        alert(`❌ OpenAI Test FAILED. Check the error message on the dashboard.`);
    } finally {
        setProcessing(false);
    }
  };

  if (!dashboard) {
    return (<div className="min-h-screen bg-gray-50 flex items-center justify-center"><div className="text-center"><Activity className="w-12 h-12 text-gray-400 animate-pulse mx-auto mb-4" /><p className="text-gray-500">Connecting to AI Agent...</p><p className="text-xs text-gray-400 mt-2">API: {API_URL}</p></div></div>);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4"><div className="flex justify-between items-center"><div className="flex items-center space-x-3"><div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl"><Sparkles className="w-6 h-6 text-white" /></div><div><h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">AI SEO Content Agent</h1><p className="text-xs text-gray-600">API: {API_URL}</p></div></div><div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} shadow-lg`}><div className="flex items-center space-x-2">{dashboard.system.is_paused ? (<><div className="w-2 h-2 bg-red-500 rounded-full"></div><span>PAUSED</span></>) : (<><div className="w-2 h-2 bg-green-500 rounded-full relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping"></div><span>ACTIVE</span></>)}</div></div></div></div>
      </header>
      
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {errMsg && <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm break-all">{errMsg}</div>}
        
        <div className="flex flex-wrap gap-3">
          <ActionButton onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search className="w-4 h-4" />} label="Scan All" gradient="from-blue-500 to-cyan-500" />
          <ActionButton onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap className="w-4 h-4" />} label="Process Queue" gradient="from-green-500 to-emerald-500" />
          <ActionButton onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />} label={dashboard.system.is_paused ? "Resume" : "Pause"} gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"} />
          <ActionButton onClick={testOpenAI} disabled={processing} icon={<TestTube2 className="w-4 h-4" />} label="Test OpenAI" gradient="from-orange-500 to-yellow-500" />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard title="Products" stats={dashboard.stats.products} icon={<Package className="w-5 h-5" />} gradient="from-blue-500 to-cyan-500" />
          <StatCard title="Collections" stats={dashboard.stats.collections} icon={<Layers className="w-5 h--5" />} gradient="from-purple-500 to-pink-500" />
          <StatCard title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} gradient="from-orange-500 to-red-500" />
          <StatCard title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'} icon={<Clock className="w-5 h-5" />} gradient="from-green-500 to-emerald-500" />
        </div>
        
        {/* ... other components ... */}
      </main>
    </div>
  );
}

// --- Self-Contained Components ---
interface StatCardProps { title: string; stats?: { total: number; completed: number; pending: number; }; value?: string | number; icon: React.ReactNode; gradient: string; }
const StatCard: React.FC<StatCardProps> = ({ title, stats, value, icon, gradient }) => { const total = stats?.total ?? value ?? 0; const completed = stats?.completed ?? 0; const pending = stats?.pending ?? 0; return (<div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"><div className="flex items-center justify-between mb-4"><h3 className="text-sm font-medium text-gray-600">{title}</h3><div className={`p-2 bg-gradient-to-br ${gradient} rounded-lg text-white`}>{icon}</div></div>{stats ? (<div><p className="text-3xl font-bold text-gray-900">{total}</p><div className="flex space-x-4 mt-2 text-xs"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div></div>) : (<p className="text-3xl font-bold text-gray-900">{total}</p>)}</div>); };
interface ActionButtonProps { onClick: () => void; disabled?: boolean; icon: React.ReactNode; label: string; gradient: string; }
const ActionButton: React.FC<ActionButtonProps> = ({ onClick, disabled = false, icon, label, gradient }) => (<button onClick={onClick} disabled={disabled} className={`px-6 py-3 bg-gradient-to-r ${gradient} text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}>{icon}<span>{label}</span></button>);
// ... (rest of the components)
