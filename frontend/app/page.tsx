'use client';

import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  RefreshCw, Activity, Package, Clock, CheckCircle, PlayCircle, Search,
  PauseCircle, TrendingUp, FileText, Plus, Layers, Sparkles, Zap, Edit3, Trash2, Terminal
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// THE NEW LIVE LOG FEED COMPONENT
function LiveLogFeed() {
  const [logs, setLogs] = useState([]);
  const logContainerRef = useRef(null);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await axios.get(`${API_URL}/api/live-logs`);
        setLogs(response.data.logs.reverse()); // Show newest first
      } catch (error) {
        // Silently fail, don't spam console
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 3000); // Poll every 3 seconds
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Auto-scroll to bottom
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="bg-gray-900 text-white rounded-2xl shadow-xl overflow-hidden h-full flex flex-col">
      <div className="px-6 py-4 bg-gray-800 border-b border-gray-700 flex items-center space-x-2">
        <Terminal className="w-5 h-5 text-green-400" />
        <h2 className="text-lg font-semibold text-gray-200">Live Activity Feed</h2>
      </div>
      <div ref={logContainerRef} className="p-4 space-y-2 overflow-y-auto font-mono text-sm flex-grow">
        {logs.length === 0 ? (
          <p className="text-gray-500">Awaiting activity...</p>
        ) : (
          logs.map((log, index) => (
            <div key={index} className="flex">
              <span className="text-gray-500 mr-2">{new Date(log.timestamp).toLocaleTimeString()}</span>
              <span className={`${
                log.level === 'ERROR' ? 'text-red-400' : 
                log.level === 'WARN' ? 'text-yellow-400' : 'text-gray-300'
              }`}>
                [{log.level}]
              </span>
              <p className="flex-1 ml-2 break-all">{log.message}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}


export default function Dashboard() {
    // ... all your existing useState and useEffect hooks ...
    const [dashboard, setDashboard] = useState({ system: {}, stats: { products: {}, collections: {} }, recent_activity: [] });
    const [processing, setProcessing] = useState(false);

    const scanAll = async () => {
        setProcessing(true);
        // ... rest of your scanAll function
        try {
            await axios.post(`${API_URL}/api/scan`);
        } finally {
            setProcessing(false);
        }
    };
    
    // ... all your other functions (togglePause, addToManualQueue, etc.)

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 via-purple-50 to-pink-50">
            {/* ... Your existing Header and Navigation Tabs ... */}
             <header className="sticky top-0 z-50 backdrop-blur-xl bg-white/80 border-b border-white/20">
                {/* Your header JSX */}
            </header>
            <div className="max-w-7xl mx-auto px-6 py-6">
                 {/* Your tabs JSX */}
            </div>
            
            <div className="max-w-7xl mx-auto px-6 pb-12">
                {/* Main Content Grid - REPLACED WITH A NEW LAYOUT */}
                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                    {/* Left Column (3/5 width) */}
                    <div className="lg:col-span-3 space-y-6">
                        {/* Stats Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                           {/* ... All your StatCard components ... */}
                        </div>

                        {/* Action Buttons */}
                        <div className="flex flex-wrap gap-3">
                           {/* ... All your ActionButton components ... */}
                           <button onClick={scanAll} disabled={processing}>Scan All</button>
                        </div>
                        
                        {/* Recent Activity */}
                        <div>
                           {/* ... Your Recent Activity component ... */}
                        </div>
                    </div>

                    {/* Right Column (2/5 width) - THE NEW LOG FEED */}
                    <div className="lg:col-span-2">
                        <LiveLogFeed />
                    </div>
                </div>
            </div>

             {/* ... Your Modal component ... */}
        </div>
    );
}

// ... All your other self-contained components (StatCard, ActionButton, Modal, etc.) ...
