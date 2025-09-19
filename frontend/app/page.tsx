'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle,
  PlayCircle, Search, PauseCircle, AlertTriangle, TrendingUp,
  FileText, Plus, Layers, Sparkles, Zap, Target, Edit3, Trash2
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Define types for our data to help TypeScript
interface SystemState {
  is_paused?: boolean;
  auto_pause_triggered?: boolean;
  last_scan?: string;
  products_found_in_last_scan?: number;
  collections_found_in_last_scan?: number;
}
interface StatsBlock { total?: number; completed?: number; pending?: number; }
interface Stats {
  products?: StatsBlock;
  collections?: StatsBlock;
  manual_queue?: number;
  processed_today?: number;
  total_completed?: number;
}
interface ActivityItemData {
  id: string;
  type: 'product' | 'collection';
  title: string;
  status: string;
  updated?: string;
}
interface DashboardData {
  system: SystemState;
  stats: Stats;
  recent_activity: ActivityItemData[];
}
interface LogData {
  item_id: string;
  item_type: string;
  item_title: string;
  keywords_used?: string[];
  generated_at: string;
}
interface ManualQueueItemData {
  id: number;
  item_id: string;
  item_type: string;
  title: string;
  reason: string;
  created_at: string;
}

export default function Dashboard() {
  const [dashboard, setDashboard] = useState<DashboardData>({ system: {}, stats: { products: {}, collections: {} }, recent_activity: [] });
  const [logs, setLogs] = useState<LogData[]>([]);
  const [manualQueue, setManualQueue] = useState<ManualQueueItemData[]>([]);
  const [processing, setProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newItem, setNewItem] = useState({ item_id: '', item_type: 'product', title: '', url: '', reason: 'revision' });

  const fetchData = async () => {
    try {
      const [dashRes, logsRes, queueRes] = await Promise.all([
        axios.get(`${API_URL}/api/dashboard`),
        axios.get(`${API_URL}/api/logs`),
        axios.get(`${API_URL}/api/manual-queue`)
      ]);
      setDashboard(dashRes.data);
      setLogs(logsRes.data.logs);
      setManualQueue(queueRes.data.items);
    } catch (e) { console.error("Failed to fetch data:", e); }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleApiCall = async (apiCall: () => Promise<any>) => {
    if (processing) return;
    setProcessing(true);
    try { await apiCall(); } 
    catch (e) { console.error("API call failed:", e); alert("An error occurred."); }
    setTimeout(() => { fetchData(); setProcessing(false); }, 3000);
  };

  const scanAll = () => handleApiCall(() => axios.post(`${API_URL}/api/scan`));
  const processQueue = () => handleApiCall(() => axios.post(`${API_URL}/api/process-queue`));
  const togglePause = () => handleApiCall(() => axios.post(`${API_URL}/api/pause`));
  const addToManualQueue = () => { handleApiCall(() => axios.post(`${API_URL}/api/manual-queue`, newItem)); setShowAddModal(false); };
  const removeFromQueue = (id: number) => handleApiCall(() => axios.delete(`${API_URL}/api/manual-queue/${id}`));
  const generateContent = (item_id: string, item_type: string) => handleApiCall(() => axios.post(`${API_URL}/api/generate-content`, { item_id, item_type, regenerate: true }));

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl shadow-lg"><Sparkles className="w-6 h-6 text-white" /></div>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">AI SEO Agent</h1>
              <p className="text-sm text-gray-600">Automated Content for Shopify</p>
            </div>
          </div>
          <div className={`px-6 py-3 rounded-2xl font-medium transition-all ${dashboard.system.is_paused ? 'bg-red-100 text-red-700 shadow-red-200' : 'bg-green-100 text-green-700 shadow-green-200'} shadow-lg`}>
            <div className="flex items-center space-x-2">
              <div className={`w-2 h-2 rounded-full ${dashboard.system.is_paused ? 'bg-red-500' : 'bg-green-500 relative before:absolute before:-inset-1 before:bg-current before:rounded-full before:opacity-75 before:animate-ping'}`}></div>
              <span>{dashboard.system.is_paused ? "PAUSED" : "ACTIVE"}</span>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex space-x-1 p-1 bg-white/50 backdrop-blur-sm rounded-2xl shadow-inner">
          {['overview', 'manual', 'logs'].map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)} className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${activeTab === tab ? 'bg-white text-purple-600 shadow-lg' : 'text-gray-600 hover:text-gray-900'}`}>
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-6 pb-12">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard title="Products" stats={dashboard.stats.products} icon={<Package />} gradient="from-blue-500 to-cyan-500" />
              <StatCard title="Collections" stats={dashboard.stats.collections} icon={<Layers />} gradient="from-purple-500 to-pink-500" />
              <StatCard title="Manual Queue" value={dashboard.stats.manual_queue} icon={<Edit3 />} gradient="from-orange-500 to-red-500" />
              <StatCard title="Today's Progress" value={dashboard.stats.processed_today} icon={<TrendingUp />} gradient="from-green-500 to-emerald-500" />
            </div>
            <div className="flex flex-wrap gap-3">
              <ActionButton onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search />} label="Scan All" gradient="from-blue-500 to-cyan-500" />
              <ActionButton onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap />} label="Process Queue" gradient="from-green-500 to-emerald-500" />
              <ActionButton onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle /> : <PauseCircle />} label={dashboard.system.is_paused ? "Resume" : "Pause"} gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"} />
              <ActionButton onClick={() => setShowAddModal(true)} icon={<Plus />} label="Add to Queue" gradient="from-purple-500 to-pink-500" />
            </div>
            <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden">
              <div className="px-6 py-4 bg-gradient-to-r from-purple-500 to-pink-500"><h2 className="text-lg font-semibold text-white">Recent Activity</h2></div>
              <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
                {dashboard.recent_activity.length > 0 ? dashboard.recent_activity.map(item => <ActivityItem key={`${item.type}-${item.id}`} item={item} onRegenerate={generateContent} />) : <div className="p-12 text-center text-gray-500"><Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" /><p>No activity yet</p></div>}
              </div>
            </div>
          </div>
        )}
        {activeTab === 'manual' && (
          <div className="space-y-6">
            <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-12 text-center">
                <Edit3 className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p className="text-gray-500">Manual Queue Feature Coming Soon</p>
            </div>
          </div>
        )}
        {activeTab === 'logs' && (
          <div className="space-y-6">
             <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-12 text-center">
                <FileText className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p className="text-gray-500">Logs Feature Coming Soon</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// --- Self-Contained Components (Restoring the Modern UI) ---
const StatCard = ({ title, stats, value, icon, gradient }: { title: string, stats?: any, value?: any, icon: React.ReactNode, gradient: string }) => {
  const total = stats?.total ?? value ?? 0;
  const completed = stats?.completed ?? 0;
  const pending = stats?.pending ?? 0;
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-600">{title}</h3>
        <div className={`p-2 bg-gradient-to-br ${gradient} rounded-lg text-white`}>{icon}</div>
      </div>
      {stats ? (<div><p className="text-3xl font-bold text-gray-900">{total}</p><div className="flex space-x-4 mt-2 text-xs"><span className="text-green-600">✓ {completed}</span><span className="text-yellow-600">⏳ {pending}</span></div></div>) 
      : (<p className="text-3xl font-bold text-gray-900">{total}</p>)}
    </div>
  );
};

const ActionButton = ({ onClick, disabled = false, icon, label, gradient }: { onClick: () => void, disabled?: boolean, icon: React.ReactNode, label: string, gradient: string }) => (
  <button onClick={onClick} disabled={disabled} className={`px-6 py-3 bg-gradient-to-r ${gradient} text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}>
    {icon} <span>{label}</span>
  </button>
);

const ActivityItem = ({ item, onRegenerate }: { item: ActivityItemData, onRegenerate: (id: string, type: string) => void }) => (
    <div className="p-4 hover:bg-gray-50 transition-colors">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center space-x-2">{item.type === 'collection' ? <Layers className="w-4 h-4 text-purple-500" /> : <Package className="w-4 h-4 text-blue-500" />}<h3 className="font-medium text-gray-900">{item.title}</h3></div>
          <div className="flex items-center space-x-4 mt-2"><StatusBadge status={item.status} /><span className="text-xs text-gray-500">ID: {item.id}</span>{item.updated && (<span className="text-xs text-gray-500">{new Date(item.updated).toLocaleString()}</span>)}</div>
        </div>
        <button onClick={() => onRegenerate(item.id, item.type)} className="p-2 text-gray-400 hover:text-purple-600 transition-colors" title="Regenerate content"><RefreshCw className="w-4 h-4" /></button>
      </div>
    </div>
);

const StatusBadge = ({ status }: { status: string }) => {
  const styles: { [key: string]: string } = {
    pending: 'bg-yellow-100 text-yellow-700', processing: 'bg-blue-100 text-blue-700', completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700', skipped: 'bg-gray-100 text-gray-700', revision: 'bg-purple-100 text-purple-700'
  };
  return (<span className={`px-2 py-1 text-xs font-medium rounded-full ${styles[status] || 'bg-gray-100'}`}>{status}</span>);
};
