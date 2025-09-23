'use client';

import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search,
  PauseCircle, AlertTriangle, TrendingUp, FileText, Plus, Layers, Sparkles,
  Zap, Target, Edit3, Trash2, TestTube2
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Define a specific type for the tabs to satisfy TypeScript
type TabType = 'overview' | 'manual' | 'logs';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [manualQueue, setManualQueue] = useState<any[]>([]);
  const [processing, setProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newItem, setNewItem] = useState({ item_id: '', item_type: 'product', title: '', url: '', reason: 'revision' });
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
  const fetchLogs = async () => {
    try { const res = await safe(() => api.get('/api/logs')); if (res && res.data) setLogs(res.data.logs || []); } catch (e) {}
  };
  const fetchManualQueue = async () => {
    try { const res = await safe(() => api.get('/api/manual-queue')); if (res && res.data) setManualQueue(res.data.items || []); } catch (e) {}
  };

  useEffect(() => {
    fetchDashboard(); fetchLogs(); fetchManualQueue();
    const id = setInterval(() => {
      fetchDashboard();
      if (activeTab === 'logs') fetchLogs();
      if (activeTab === 'manual') fetchManualQueue();
    }, 10000);
    return () => clearInterval(id);
  }, [activeTab]);

  const handleApiAction = async (fn: () => Promise<any>) => {
    if (processing) return;
    setProcessing(true);
    try {
      await safe(fn);
      setTimeout(() => {
        fetchDashboard();
        fetchLogs();
        fetchManualQueue();
        setProcessing(false);
      }, 2000);
    } catch {
      setProcessing(false);
    }
  };

  const scanAll = () => handleApiAction(() => api.post('/api/scan'));
  const processQueue = () => handleApiAction(() => api.post('/api/process-queue'));
  const togglePause = () => handleApiAction(() => api.post('/api/pause'));
  const addToManualQueue = () => {
    handleApiAction(() => api.post('/api/manual-queue', newItem));
    setShowAddModal(false);
    setNewItem({ item_id: '', item_type: 'product', title: '', url: '', reason: 'revision'});
  };
  const removeFromQueue = (id: number) => handleApiAction(() => api.delete(`/api/manual-queue/${id}`));
  const generateContent = (item_id: string, item_type: string) => handleApiAction(() => api.post(`/api/generate-content`, { item_id, item_type, regenerate: true }));
  const testOpenAI = async () => {
    setProcessing(true);
    try {
        const res = await safe(() => api.post('/api/test-openai', { prompt: 'say hello world' }));
        alert(`✅ OpenAI Test SUCCESS!\n\nResponse: "${res.data.response}"`);
    } catch (e: any) {
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
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl"><Sparkles className="w-6 h-6 text-white" /></div>
              <div><h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">AI SEO Content Agent</h1><p className="text-xs text-gray-600">API: {API_URL}</p></div>
            </div>
            <div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} shadow-lg`}>
              <div className="flex items-center space-x-2">{dashboard.system.is_paused ? (<><div className="w-2 h-2 bg-red-500 rounded-full"></div><span>PAUSED</span></>) : (<><div className="w-2 h-2 bg-green-500 rounded-full relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping"></div><span>ACTIVE</span></>)}</div>
            </div>
          </div>
        </div>
      </header>
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex space-x-1 p-1 bg-white/50 backdrop-blur-sm rounded-2xl shadow-inner">
          {(['overview', 'manual', 'logs'] as TabType[]).map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)} className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${activeTab === tab ? 'bg-white text-purple-600 shadow-lg' : 'text-gray-600 hover:text-gray-900'}`}>{tab.charAt(0).toUpperCase() + tab.slice(1)}</button>
          ))}
        </div>
      </div>
      <main className="max-w-7xl mx-auto px-6 pb-12 space-y-6">
        {errMsg && <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm break-all">{errMsg}</div>}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-3">
              <ActionButton onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search className="w-4 h-4" />} label="Scan All" gradient="from-blue-500 to-cyan-500" />
              <ActionButton onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap className="w-4 h-4" />} label="Process Queue" gradient="from-green-500 to-emerald-500" />
              <ActionButton onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />} label={dashboard.system.is_paused ? "Resume" : "Pause"} gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"} />
              <ActionButton onClick={testOpenAI} disabled={processing} icon={<TestTube2 className="w-4 h-4" />} label="Test OpenAI" gradient="from-orange-500 to-yellow-500" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <StatCard title="Products" stats={dashboard.stats.products} icon={<Package className="w-5 h-5" />} gradient="from-blue-500 to-cyan-500" />
              <StatCard title="Collections" stats={dashboard.stats.collections} icon={<Layers className="w-5 h-5" />} gradient="from-purple-500 to-pink-500" />
              <StatCard title="Manual Queue" value={dashboard.stats.manual_queue} icon={<Edit3 className="w-5 h-5" />} gradient="from-orange-500 to-red-500" />
              <StatCard title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} gradient="from-green-500 to-emerald-500" />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2"><div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden"><div className="px-6 py-4 bg-gradient-to-r from-purple-500 to-pink-500"><h2 className="text-lg font-semibold text-white">Recent Activity</h2></div><div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">{!dashboard.recent_activity || dashboard.recent_activity.length === 0 ? (<div className="p-12 text-center text-gray-500"><Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" /><p>No activity yet</p></div>) : (dashboard.recent_activity.map((item: any) => (<ActivityItem key={`${item.type}-${item.id}`} item={item} onRegenerate={generateContent} />)))}</div></div></div>
              <div className="space-y-4"><InfoCard title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'} icon={<Clock className="w-5 h-5" />} /><InfoCard title="Found in Last Scan" value={`${dashboard.system.products_found_in_last_scan} products, ${dashboard.system.collections_found_in_last_scan} collections`} icon={<Search className="w-5 h-5" />} /><InfoCard title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} /></div>
            </div>
          </div>
        )}
        {activeTab === 'manual' && (<div className="space-y-6"><div className="flex justify-between items-center"><h2 className="text-2xl font-bold text-gray-900">Manual Queue</h2><button onClick={() => setShowAddModal(true)} className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:shadow-lg transition-all"><Plus className="w-5 h-5 inline mr-2" />Add Item</button></div><div className="grid gap-4">{!manualQueue || manualQueue.length === 0 ? (<div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-12 text-center"><Edit3 className="w-12 h-12 mx-auto mb-3 text-gray-300" /><p className="text-gray-500">No items in manual queue</p></div>) : (manualQueue.map((item: any) => (<QueueItem key={item.id} item={item} onRemove={removeFromQueue} />)))}</div></div>)}
        {activeTab === 'logs' && (<div className="space-y-6"><h2 className="text-2xl font-bold text-gray-900">Generation Logs</h2><div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden"><div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">{!logs || logs.length === 0 ? (<div className="p-12 text-center text-gray-500"><FileText className="w-12 h-12 mx-auto mb-3 text-gray-300" /><p>No content generated yet</p></div>) : (logs.map((log: any, index: number) => (<LogItem key={index} log={log} />)))}</div></div></div>)}
      </main>
      {showAddModal && (<Modal onClose={() => setShowAddModal(false)}><div className="p-6">...</div></Modal>)}
    </div>
  );
}

// --- Self-Contained Components ---
interface StatCardProps { title: string; stats?: { total: number; completed: number; pending: number; }; value?: string | number; icon: React.ReactNode; gradient: string; }
const StatCard: React.FC<StatCardProps> = ({ title, stats, value, icon, gradient }) => { const total = stats?.total ?? value ?? 0; const completed = stats?.completed ?? 0; const pending = stats?.pending ?? 0; return (<div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"><div className="flex items-center justify-between mb-4"><h3 className="text-sm font-medium text-gray-600">{title}</h3><div className={`p-2 bg-gradient-to-br ${gradient} rounded-lg text-white`}>{icon}</div></div>{stats ? (<div><p className="text-3xl font-bold text-gray-900">{total}</p><div className="flex space-x-4 mt-2 text-xs"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div></div>) : (<p className="text-3xl font-bold text-gray-900">{total}</p>)}</div>); };
interface ActionButtonProps { onClick: () => void; disabled?: boolean; icon: React.ReactNode; label: string; gradient: string; }
const ActionButton: React.FC<ActionButtonProps> = ({ onClick, disabled = false, icon, label, gradient }) => (<button onClick={onClick} disabled={disabled} className={`px-6 py-3 bg-gradient-to-r ${gradient} text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}>{icon}<span>{label}</span></button>);
interface ActivityItemProps { item: any; onRegenerate: (id: string, type: string) => void; }
const ActivityItem: React.FC<ActivityItemProps> = ({ item, onRegenerate }) => (<div className="p-4 hover:bg-gray-50 transition-colors"><div className="flex justify-between items-start"><div className="flex-1"><div className="flex items-center space-x-2">{item.type === 'collection' ? <Layers className="w-4 h-4 text-purple-500" /> : <Package className="w-4 h-4 text-blue-500" />}<h3 className="font-medium text-gray-900">{item.title}</h3></div><div className="flex items-center space-x-4 mt-2"><StatusBadge status={item.status} /><span className="text-xs text-gray-500">ID: {item.id}</span>{item.updated && (<span className="text-xs text-gray-500">{new Date(item.updated).toLocaleString()}</span>)}</div></div><button onClick={() => onRegenerate(item.id, item.type)} className="p-2 text-gray-400 hover:text-purple-600 transition-colors" title="Regenerate content"><RefreshCw className="w-4 h-4" /></button></div></div>);
interface QueueItemProps { item: any; onRemove: (id: number) => void; }
const QueueItem: React.FC<QueueItemProps> = ({ item, onRemove }) => (<div className="bg-white/80 backdrop-blur-sm rounded-xl shadow-lg p-4 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"><div className="flex justify-between items-start"><div><div className="flex items-center space-x-2"><Target className="w-4 h-4 text-purple-500" /><h3 className="font-medium text-gray-900">{item.title}</h3></div><div className="flex items-center space-x-4 mt-2 text-sm text-gray-500"><span className="px-2 py-1 bg-purple-100 text-purple-700 rounded-full text-xs">{item.item_type}</span><span>{item.reason}</span><span>{new Date(item.created_at).toLocaleString()}</span></div></div><button onClick={() => onRemove(item.id)} className="p-2 text-gray-400 hover:text-red-600 transition-colors"><Trash2 className="w-4 h-4" /></button></div></div>);
interface LogItemProps { log: any; }
const LogItem: React.FC<LogItemProps> = ({ log }) => (<div className="p-4 hover:bg-gray-50 transition-colors"><div className="flex items-start space-x-3"><div className="p-2 bg-green-100 rounded-lg"><Zap className="w-4 h-4 text-green-600" /></div><div className="flex-1"><h4 className="font-medium text-gray-900">{log.item_title}</h4><div className="flex items-center space-x-2 mt-1"><span className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs">{log.item_type}</span></div><p className="text-xs text-gray-400 mt-1">{new Date(log.generated_at).toLocaleString()}</p></div></div></div>);
interface InfoCardProps { title: string; value: string | number; icon: React.ReactNode; }
const InfoCard: React.FC<InfoCardProps> = ({ title, value, icon }) => (<div className="bg-white/80 backdrop-blur-sm rounded-xl shadow-lg p-4"><div className="flex items-center space-x-3"><div className="p-2 bg-gray-100 rounded-lg">{icon}</div><div><p className="text-xs text-gray-500">{title}</p><p className="text-sm font-medium text-gray-900">{value}</p></div></div></div>);
interface StatusBadgeProps { status: string; }
const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => { const styles: any = { pending: 'bg-yellow-100 text-yellow-700', processing: 'bg-blue-100 text-blue-700', completed: 'bg-green-100 text-green-700', failed: 'bg-red-100 text-red-700', skipped: 'bg-gray-100 text-gray-700', revision: 'bg-purple-100 text-purple-700' }; return (<span className={`px-2 py-1 text-xs font-medium rounded-full ${styles[status] || 'bg-gray-100 text-gray-700'}`}>{status}</span>); };
interface ModalProps { children: React.ReactNode; onClose: () => void; }
const Modal: React.FC<ModalProps> = ({ children, onClose }) => (<div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50"><div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4">{children}</div><div className="fixed inset-0 -z-10" onClick={onClose}></div></div>);
