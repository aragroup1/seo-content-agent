'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  RefreshCw, 
  Activity, 
  Package, 
  Clock, 
  CheckCircle,
  PlayCircle,
  Search,
  PauseCircle,
  AlertTriangle,
  TrendingUp,
  FileText,
  Plus,
  Layers,
  Sparkles,
  Zap,
  Target,
  Edit3,
  Trash2
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const [dashboard, setDashboard] = useState({
    system: {
      is_paused: false,
      auto_pause_triggered: false,
      last_scan: null,
      products_found_in_last_scan: 0,
      collections_found_in_last_scan: 0
    },
    stats: {
      products: { total: 0, completed: 0, pending: 0 },
      collections: { total: 0, completed: 0, pending: 0 },
      manual_queue: 0,
      processed_today: 0,
      total_completed: 0
    },
    recent_activity: []
  });
  
  const [logs, setLogs] = useState([]);
  const [manualQueue, setManualQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newItem, setNewItem] = useState({
    item_id: '',
    item_type: 'product',
    title: '',
    url: '',
    reason: 'revision'
  });

  useEffect(() => {
    fetchDashboard();
    fetchLogs();
    fetchManualQueue();
    
    const interval = setInterval(() => {
      fetchDashboard();
      if (activeTab === 'logs') fetchLogs();
      if (activeTab === 'manual') fetchManualQueue();
    }, 10000);
    
    return () => clearInterval(interval);
  }, [activeTab]);

  const fetchDashboard = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/dashboard`);
      setDashboard(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
    }
  };

  const fetchLogs = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/logs`);
      setLogs(response.data.logs);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const API_URL = 'https://seo-content-agent-backend-production.up.railway.app';

  const fetchManualQueue = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/manual-queue`);
      setManualQueue(response.data.items);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const scanAll = async () => {
    setProcessing(true);
    try {
      const response = await axios.post(`${API_URL}/api/scan`);
      
      if (response.data.auto_paused) {
        alert(`⚠️ System auto-paused! Found too many new items.`);
      }
      
      setTimeout(() => {
        fetchDashboard();
        setProcessing(false);
      }, 2000);
    } catch (error) {
      console.error('Error:', error);
      setProcessing(false);
    }
  };

const testConnection = async () => {
  try {
    console.log('Testing connection to:', API_URL);
    const response = await axios.get(`${API_URL}/api/health`);
    console.log('Health check response:', response.data);
    alert(`✅ Connection successful!\n\nServices Status:\n${JSON.stringify(response.data.services, null, 2)}`);
  } catch (error: any) {
    console.error('Connection test failed:', error);
    alert(`❌ Connection failed!\n\nAPI URL: ${API_URL}\nError: ${error.message}`);
  }
};
  
  const togglePause = async () => {
    try {
      await axios.post(`${API_URL}/api/pause`);
      fetchDashboard();
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const addToManualQueue = async () => {
    try {
      await axios.post(`${API_URL}/api/manual-queue`, newItem);
      setShowAddModal(false);
      setNewItem({
        item_id: '',
        item_type: 'product',
        title: '',
        url: '',
        reason: 'revision'
      });
      fetchManualQueue();
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const removeFromQueue = async (id: number) => {
    try {
      await axios.delete(`${API_URL}/api/manual-queue/${id}`);
      fetchManualQueue();
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const generateContent = async (item_id: string, item_type: string) => {
    try {
      await axios.post(`${API_URL}/api/generate-content`, {
        item_id,
        item_type,
        regenerate: true
      });
      fetchDashboard();
      fetchLogs();
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
      {/* Modern Header */}
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
                <p className="text-sm text-gray-600">Intelligent content generation for Shopify</p>
              </div>
            </div>
            
            {/* System Status */}
            <div className={`px-6 py-3 rounded-2xl font-medium transition-all ${
              dashboard.system.is_paused 
                ? 'bg-red-100 text-red-700 shadow-red-200' 
                : 'bg-green-100 text-green-700 shadow-green-200'
            } shadow-lg`}>
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

      {/* Navigation Tabs */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex space-x-1 p-1 bg-white/50 backdrop-blur-sm rounded-2xl shadow-inner">
          {['overview', 'manual', 'logs'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${
                activeTab === tab
                  ? 'bg-white text-purple-600 shadow-lg'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 pb-12">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                title="Products"
                stats={dashboard.stats.products}
                icon={<Package className="w-5 h-5" />}
                gradient="from-blue-500 to-cyan-500"
              />
              <StatCard
                title="Collections"
                stats={dashboard.stats.collections}
                icon={<Layers className="w-5 h-5" />}
                gradient="from-purple-500 to-pink-500"
              />
              <StatCard
                title="Manual Queue"
                value={dashboard.stats.manual_queue}
                icon={<Edit3 className="w-5 h-5" />}
                gradient="from-orange-500 to-red-500"
              />
              <StatCard
                title="Today's Progress"
                value={dashboard.stats.processed_today}
                icon={<TrendingUp className="w-5 h-5" />}
                gradient="from-green-500 to-emerald-500"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap gap-3">
              <ActionButton
                onClick={scanAll}
                disabled={processing || dashboard.system.is_paused}
                icon={<Search className="w-4 h-4" />}
                label="Scan All"
                gradient="from-blue-500 to-cyan-500"
              />
              <ActionButton
  onClick={testConnection}
  icon={<Activity className="w-4 h-4" />}
  label="Test Connection"
  gradient="from-yellow-500 to-orange-500"
/>
              
              <ActionButton
                onClick={togglePause}
                icon={dashboard.system.is_paused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />}
                label={dashboard.system.is_paused ? "Resume" : "Pause"}
                gradient={dashboard.system.is_paused ? "from-green-500 to-emerald-500" : "from-red-500 to-pink-500"}
              />
              
              <ActionButton
                onClick={() => setShowAddModal(true)}
                icon={<Plus className="w-4 h-4" />}
                label="Add to Queue"
                gradient="from-purple-500 to-pink-500"
              />
              
              <ActionButton
                onClick={() => {
                  fetchDashboard();
                  fetchLogs();
                }}
                icon={<RefreshCw className="w-4 h-4" />}
                label="Refresh"
                gradient="from-gray-500 to-gray-600"
              />
            </div>

            {/* Recent Activity */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden">
                  <div className="px-6 py-4 bg-gradient-to-r from-purple-500 to-pink-500">
                    <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
                  </div>
                  <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
                    {dashboard.recent_activity.length === 0 ? (
                      <div className="p-12 text-center text-gray-500">
                        <Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                        <p>No activity yet</p>
                      </div>
                    ) : (
                      dashboard.recent_activity.map((item: any) => (
                        <ActivityItem key={`${item.type}-${item.id}`} item={item} onRegenerate={generateContent} />
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* System Info */}
              <div className="space-y-4">
                <InfoCard
                  title="Last Scan"
                  value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleString() : 'Never'}
                  icon={<Clock className="w-5 h-5" />}
                />
                <InfoCard
                  title="Found in Last Scan"
                  value={`${dashboard.system.products_found_in_last_scan} products, ${dashboard.system.collections_found_in_last_scan} collections`}
                  icon={<Search className="w-5 h-5" />}
                />
                <InfoCard
                  title="Total Completed"
                  value={dashboard.stats.total_completed}
                  icon={<CheckCircle className="w-5 h-5" />}
                />
              </div>
            </div>
          </div>
        )}

        {/* Manual Queue Tab */}
        {activeTab === 'manual' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-900">Manual Queue</h2>
              <button
                onClick={() => setShowAddModal(true)}
                className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl hover:shadow-lg transition-all"
              >
                <Plus className="w-5 h-5 inline mr-2" />
                Add Item
              </button>
            </div>

            <div className="grid gap-4">
              {manualQueue.length === 0 ? (
                <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-12 text-center">
                  <Edit3 className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p className="text-gray-500">No items in manual queue</p>
                </div>
              ) : (
                manualQueue.map((item: any) => (
                  <QueueItem key={item.id} item={item} onRemove={removeFromQueue} />
                ))
              )}
            </div>
          </div>
        )}

        {/* Logs Tab */}
        {activeTab === 'logs' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold text-gray-900">Generation Logs</h2>
            
            <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl overflow-hidden">
              <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
                {logs.length === 0 ? (
                  <div className="p-12 text-center text-gray-500">
                    <FileText className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                    <p>No content generated yet</p>
                  </div>
                ) : (
                  logs.map((log: any, index: number) => (
                    <LogItem key={index} log={log} />
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Add to Queue Modal */}
      {showAddModal && (
        <Modal onClose={() => setShowAddModal(false)}>
          <div className="p-6">
            <h3 className="text-xl font-bold mb-4">Add to Manual Queue</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={newItem.item_type}
                  onChange={(e) => setNewItem({...newItem, item_type: e.target.value})}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                >
                  <option value="product">Product</option>
                  <option value="collection">Collection</option>
                  <option value="page">Page</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Item ID</label>
                <input
                  type="text"
                  value={newItem.item_id}
                  onChange={(e) => setNewItem({...newItem, item_id: e.target.value})}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="Shopify ID"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
                <input
                  type="text"
                  value={newItem.title}
                  onChange={(e) => setNewItem({...newItem, title: e.target.value})}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="Item title"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
                <select
                  value={newItem.reason}
                  onChange={(e) => setNewItem({...newItem, reason: e.target.value})}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                >
                  <option value="revision">Content Revision</option>
                  <option value="new">New Item</option>
                  <option value="custom">Custom Request</option>
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">URL (Optional)</label>
                <input
                  type="text"
                  value={newItem.url}
                  onChange={(e) => setNewItem({...newItem, url: e.target.value})}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="https://..."
                />
              </div>
            </div>
            
            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-900"
              >
                Cancel
              </button>
              <button
                onClick={addToManualQueue}
                className="px-6 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:shadow-lg"
              >
                Add to Queue
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// Self-contained Components
function StatCard({ title, stats, value, icon, gradient }: any) {
  const total = stats?.total || value || 0;
  const completed = stats?.completed || 0;
  const pending = stats?.pending || 0;
  
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-600">{title}</h3>
        <div className={`p-2 bg-gradient-to-br ${gradient} rounded-lg text-white`}>
          {icon}
        </div>
      </div>
      
      {stats ? (
        <div>
          <p className="text-3xl font-bold text-gray-900">{total}</p>
          <div className="flex space-x-4 mt-2 text-xs">
            <span className="text-green-600">✓ {completed}</span>
            <span className="text-yellow-600">⏳ {pending}</span>
          </div>
        </div>
      ) : (
        <p className="text-3xl font-bold text-gray-900">{total}</p>
      )}
    </div>
  );
}

function ActionButton({ onClick, disabled = false, icon, label, gradient }: any) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-6 py-3 bg-gradient-to-r ${gradient} text-white rounded-xl font-medium shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function ActivityItem({ item, onRegenerate }: any) {
  return (
    <div className="p-4 hover:bg-gray-50 transition-colors">
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center space-x-2">
            {item.type === 'collection' ? (
              <Layers className="w-4 h-4 text-purple-500" />
            ) : (
              <Package className="w-4 h-4 text-blue-500" />
            )}
            <h3 className="font-medium text-gray-900">{item.title}</h3>
          </div>
          <div className="flex items-center space-x-4 mt-2">
            <StatusBadge status={item.status} />
            <span className="text-xs text-gray-500">ID: {item.id}</span>
            {item.updated && (
              <span className="text-xs text-gray-500">
                {new Date(item.updated).toLocaleString()}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => onRegenerate(item.id, item.type)}
          className="p-2 text-gray-400 hover:text-purple-600 transition-colors"
          title="Regenerate content"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function QueueItem({ item, onRemove }: any) {
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-xl shadow-lg p-4 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl">
      <div className="flex justify-between items-start">
        <div>
          <div className="flex items-center space-x-2">
            <Target className="w-4 h-4 text-purple-500" />
            <h3 className="font-medium text-gray-900">{item.title}</h3>
          </div>
          <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500">
            <span className="px-2 py-1 bg-purple-100 text-purple-700 rounded-full text-xs">
              {item.item_type}
            </span>
            <span>{item.reason}</span>
            <span>{new Date(item.created_at).toLocaleString()}</span>
          </div>
        </div>
        <button
          onClick={() => onRemove(item.id)}
          className="p-2 text-gray-400 hover:text-red-600 transition-colors"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function LogItem({ log }: any) {
  return (
    <div className="p-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-start space-x-3">
        <div className="p-2 bg-green-100 rounded-lg">
          <Zap className="w-4 h-4 text-green-600" />
        </div>
        <div className="flex-1">
          <h4 className="font-medium text-gray-900">{log.item_title}</h4>
          <div className="flex items-center space-x-2 mt-1">
            <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs">
              {log.item_type}
            </span>
            <span className="text-xs text-gray-500">
              Keywords: {log.keywords_used?.slice(0, 3).join(', ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {new Date(log.generated_at).toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}

function InfoCard({ title, value, icon }: any) {
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-xl shadow-lg p-4">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-gray-100 rounded-lg">
          {icon}
        </div>
        <div>
          <p className="text-xs text-gray-500">{title}</p>
          <p className="text-sm font-medium text-gray-900">{value}</p>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: any) {
  const styles: any = {
    pending: 'bg-yellow-100 text-yellow-700',
    processing: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    skipped: 'bg-gray-100 text-gray-700',
    revision: 'bg-purple-100 text-purple-700'
  };
  
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${styles[status] || 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  );
}

function Modal({ children, onClose }: any) {
  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4">
        {children}
      </div>
      <div className="fixed inset-0 -z-10" onClick={onClose}></div>
    </div>
  );
}
