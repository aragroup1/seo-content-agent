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

  const processQueue = async () => {
    setProcessing(true);
    try {
      await axios.post(`${API_URL}/api/process-queue`);
      setTimeout(() => {
        fetchDashboard();
        fetchLogs();
        setProcessing(false);
      }, 2000);
    } catch (error) {
      console.error('Error:', error);
      setProcessing(false);
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
                value={null}
                icon={<Package className="w-5 h-5" />}
                gradient="from-blue-500 to-cyan-500"
              />
              <StatCard
                title="Collections"
                stats={dashboard.stats.collections}
                value={null}
                icon={<Layers className="w-5 h-5" />}
                gradient="from-purple-500 to-pink-500"
              />
              <StatCard
                title="Manual Queue"
                stats={null}
                value={dashboard.stats.manual_queue}
                icon={<Edit3 className="w-5 h-5" />}
                gradient="from-orange-500 to-red-500"
              />
              <StatCard
                title="Today's Progress"
                stats={null}
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
                onClick={processQueue}
                disabled={processing || dashboard.system.is_paused}
                icon={<Zap className="w-4 h-4" />}
                label="Process Queue"
                gradient="from-green-500 to-emerald-500"
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
