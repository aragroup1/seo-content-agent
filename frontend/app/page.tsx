'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search,
  PauseCircle, AlertTriangle, TrendingUp, FileText, Plus, Layers, Sparkles,
  Zap, Target, Edit3, Trash2 
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState({ system: { is_paused: false, auto_pause_triggered: false, last_scan: null, products_found_in_last_scan: 0, collections_found_in_last_scan: 0 }, stats: { products: { total: 0, completed: 0, pending: 0 }, collections: { total: 0, completed: 0, pending: 0 }, manual_queue: 0, processed_today: 0, total_completed: 0 }, recent_activity: [] });
  const [logs, setLogs] = useState([]);
  const [manualQueue, setManualQueue] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newItem, setNewItem] = useState({ item_id: '', item_type: 'product', title: '', url: '', reason: 'revision' });

  useEffect(() => {
    fetchDashboard(); fetchLogs(); fetchManualQueue();
    const interval = setInterval(() => {
      fetchDashboard();
      if (activeTab === 'logs') fetchLogs();
      if (activeTab === 'manual') fetchManualQueue();
    }, 10000);
    return () => clearInterval(interval);
  }, [activeTab]);

  const fetchDashboard = async () => { try { const res = await axios.get(`${API_URL}/api/dashboard`); setDashboard(res.data); } catch (e) { console.error(e) }};
  const fetchLogs = async () => { try { const res = await axios.get(`${API_URL}/api/logs`); setLogs(res.data.logs); } catch (e) { console.error(e) }};
  const fetchManualQueue = async () => { try { const res = await axios.get(`${API_URL}/api/manual-queue`); setManualQueue(res.data.items); } catch (e) { console.error(e) }};
  
  const handleApiCall = async (apiCall: () => Promise<any>) => {
    if (processing) return; setProcessing(true);
    try { await apiCall(); } catch (e) { console.error("API call failed:", e); alert("An error occurred."); }
    setTimeout(() => { fetchDashboard(); fetchManualQueue(); fetchLogs(); setProcessing(false); }, 3000);
  };

  const scanAll = () => handleApiCall(() => axios.post(`${API_URL}/api/scan`));
  const processQueue = () => handleApiCall(() => axios.post(`${API_URL}/api/process-queue`));
  const togglePause = () => handleApiCall(() => axios.post(`${API_URL}/api/pause`));
  const addToManualQueue = () => { handleApiCall(() => axios.post(`${API_URL}/api/manual-queue`, newItem)); setShowAddModal(false); setNewItem({ item_id: '', item_type: 'product', title: '', url: '', reason: 'revision'}); };
  const removeFromQueue = (id: number) => handleApiCall(() => axios.delete(`${API_URL}/api/manual-queue/${id}`));
  const generateContent = (item_id: string, item_type: string) => handleApiCall(() => axios.post(`${API_URL}/api/generate-content`, { item_id, item_type, regenerate: true }));
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4"><div className="flex justify-between items-center"><div className="flex items-center space-x-3"><div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl"><Sparkles className="w-6 h-6 text-white" /></div><div><h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">AI SEO Content Agent</h1><p className="text-sm text-gray-600">Cost-Effective Content Generation</p></div></div><div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700 shadow-red-200' : 'bg-green-100 text-green-700 shadow-green-200'} shadow-lg`}><div className="flex items-center space-x-2">{dashboard.system.is_paused ? (<><div className="w-2 h-2 bg-red-500 rounded-full"></div><span>PAUSED</span></>) : (<><div className="w-2 h-2 bg-green-500 rounded-full relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping"></div><span>ACTIVE</span></>)}</div></div></div></div>
      </header>
      <div className="max-w-7xl mx-auto px-6 py-6"><div className="flex space-x-1 p-1 bg-white/50 backdrop-blur-sm rounded-2xl shadow-inner">{['overview', 'manual', 'logs'].map((tab) => (<button key={tab} onClick={() => setActiveTab(tab)} className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${activeTab === tab ? 'bg-white text-purple-600 shadow-lg' : 'text-gray-600 hover:text-gray-900'}`}>{tab.charAt(0).toUpperCase() + tab.slice(1)}</button>))}</div></div>
      <main className="max-w-7xl mx-auto px-6 pb-12">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard title="Products" stats={dashboard.stats.products} icon={<Package className="w-5 h-5" />} gradient="from-blue-500 to-cyan-500" />
              <StatCard title="Collections" stats={dashboard.stats.collections} icon={<Layers className="w-5 h-5" />} gradient="from-purple-500 to-pink-500" />
              <StatCard title="Manual Queue" value={dashboard.stats.manual_queue} icon={<Edit3 className="w-5 h-5" />} gradient="from-orange-500 to-red-500" />
              <StatCard title="Today's Progress" value={dashboard.stats.processed_today} icon={<TrendingUp className="w-5 h-5" />} gradient="from-green-500 to-emerald-500" />
            </div>
            <div className="flex flex-wrap gap-3">
              <ActionButton onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search className="w-4 h-4" />} label="Scan All" gradient="from-blue-500 to-cyan-500" />
              <ActionButton onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap className="w-4 h-4" />} label="Process Queue" gradient="from-green-500 to-emerald-500" />
              <ActionButton onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />} label={dashboard.system.is_paused ? "Resume" : "Pause"} gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"} />
              <ActionButton onClick={() => setShowAddModal(true)} icon={<Plus className="w-4 h-4" />} label="Add to Queue" gradient="from-purple-500 to-pink-500" />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2"><div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden"><div className="px-6 py-4 bg-gradient-to-r from-purple-500 to-pink-500"><h2 className="text-lg font-semibold text-white">Recent Activity</h2></div><div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">{!dashboard.recent_activity || dashboard.recent_activity.length === 0 ? (<div className="p-12 text-center text-gray-500"><Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" /><p>No activity yet</p></div>) : (dashboard.recent_activity.map((item: any) => (<ActivityItem key={`${item.type}-${item.id}`} item={item} onRegenerate={generateContent} />)))}</div></div></div>
              <div className="space-y-4"><InfoCard title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'} icon={<Clock className="w-5 h-5" />} /><InfoCard title="Found in Last Scan" value={`${dashboard.system.products_found_in_last_scan} products, ${dashboard.system.collections_found_in_last_scan} collections`} icon={<Search className="w-5 h-5" />} /><InfoCard title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle className="w-5 h-5" />} /></div>
            </div>
          </div>
        )}
        {activeTab === 'manual' && (<div className="space-y-6">...</div>)}
        {activeTab === 'logs' && (<div className="space-y-6">...</div>)}
      </main>
      {showAddModal && (<Modal onClose={() => setShowAddModal(false)}>...</Modal>)}
    </div>
  );
}

// --- Self-Contained Components ---
interface StatCardProps { title: string; stats?: { total: number; completed: number; pending: number; }; value?: string | number; icon: React.ReactNode; gradient: string; }
const StatCard: React.FC<StatCardProps> = ({ title, stats, value, icon, gradient }) => { const total = stats?.total ?? value ?? 0; const completed = stats?.completed ?? 0; const pending = stats?.pending ?? 0; return (<div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"><div className="flex items-center justify-between mb-4"><h3 className="text-sm font-medium text-gray-600">{title}</h3><div className={`p-2 bg-gradient-to-br ${gradient} rounded-lg text-white`}>{icon}</div></div>{stats ? (<div><p className="text-3xl font-bold text-gray-900">{total}</p><div className="flex space-x-4 mt-2 text-xs"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div></div>) : (<p className="text-3xl font-bold text-gray-900">{total}</p>)}</div>); };
interface ActionButtonProps { onClick: () => void; disabled?: boolean; icon: React.ReactNode; label: string; gradient: string; }
const ActionButton: React.FC<ActionButtonProps> = ({ onClick, disabled = false, icon, label, gradient }) => (<button onClick={onClick} disabled={disabled} className={`px-6 py-3 bg-gradient-to-r ${gradient} text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}>{icon}<span>{label}</span></button>);
// ... (The rest of the component definitions remain the same)
