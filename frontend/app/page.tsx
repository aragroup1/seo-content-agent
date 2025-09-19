'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { Zap, Search, PlayCircle, PauseCircle, Plus, RefreshCw, Layers, Package, Edit3, TrendingUp, Clock, CheckCircle, Activity, FileText, Target, Trash2 } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
    const [dashboard, setDashboard] = useState({ system: { is_paused: false }, stats: { products: {}, collections: {} }, recent_activity: [] });
    const [processing, setProcessing] = useState(false);

    const fetchDashboard = async () => {
        try {
            const res = await axios.get(`${API_URL}/api/dashboard`);
            setDashboard(res.data);
        } catch (e) {
            console.error("Failed to fetch dashboard data:", e);
        }
    };

    useEffect(() => {
        fetchDashboard();
        const interval = setInterval(fetchDashboard, 10000); // Refresh every 10 seconds
        return () => clearInterval(interval);
    }, []);

    const handleApiCall = async (apiCall) => {
        if (processing) return;
        setProcessing(true);
        try {
            await apiCall();
        } catch (e) {
            console.error("API call failed:", e);
            alert("An error occurred. Please check the console.");
        }
        setTimeout(() => {
            fetchDashboard();
            setProcessing(false);
        }, 3000); // Give backend time to process before refreshing
    };

    const scanAll = () => handleApiCall(() => axios.post(`${API_URL}/api/scan`));
    const processQueue = () => handleApiCall(() => axios.post(`${API_URL}/api/process-queue`));
    const togglePause = () => handleApiCall(() => axios.post(`${API_URL}/api/pause`));

    return (
        <div className="min-h-screen bg-gray-50 text-gray-800">
            <header className="sticky top-0 z-10 bg-white/70 backdrop-blur-lg border-b">
                <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                    <div className="flex items-center space-x-3">
                        <div className="p-2 bg-purple-600 rounded-lg"><Zap className="w-5 h-5 text-white" /></div>
                        <h1 className="text-xl font-bold text-gray-900">AI SEO Agent</h1>
                    </div>
                    <div className={`px-4 py-2 rounded-full font-medium text-sm flex items-center space-x-2 ${dashboard.system.is_paused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                        <div className={`w-2 h-2 rounded-full ${dashboard.system.is_paused ? 'bg-red-500' : 'bg-green-500 animate-pulse'}`}></div>
                        <span>{dashboard.system.is_paused ? "System Paused" : "System Active"}</span>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-6 py-8">
                <div className="flex flex-wrap gap-4 mb-8">
                    <ActionButton onClick={scanAll} disabled={processing || dashboard.system.is_paused} icon={<Search/>} label="Scan Shopify" color="blue"/>
                    <ActionButton onClick={processQueue} disabled={processing || dashboard.system.is_paused} icon={<Zap/>} label="Process Queue" color="green"/>
                    <ActionButton onClick={togglePause} disabled={processing} icon={dashboard.system.is_paused ? <PlayCircle/> : <PauseCircle/>} label={dashboard.system.is_paused ? "Resume" : "Pause"} color={dashboard.system.is_paused ? "green" : "red"}/>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    <StatCard title="Products" stats={dashboard.stats.products} icon={<Package />} />
                    <StatCard title="Collections" stats={dashboard.stats.collections} icon={<Layers />} />
                    <StatCard title="Total Completed" value={dashboard.stats.total_completed} icon={<CheckCircle />} />
                    <StatCard title="Last Scan" value={dashboard.system.last_scan ? new Date(dashboard.system.last_scan).toLocaleTimeString() : 'N/A'} icon={<Clock />} />
                </div>
                
                <div className="bg-white rounded-lg shadow-md">
                   <h2 className="text-lg font-semibold p-4 border-b">Recent Activity</h2>
                   <div className="divide-y">
                       {dashboard.recent_activity.map((item) => (
                           <ActivityItem key={`${item.type}-${item.id}`} item={item} />
                       ))}
                   </div>
                </div>
            </main>
        </div>
    );
}

// --- Self-Contained Components ---
const ActionButton = ({ onClick, disabled, icon, label, color }) => {
    const colors = {
        blue: 'bg-blue-600 hover:bg-blue-700',
        green: 'bg-green-600 hover:bg-green-700',
        red: 'bg-red-600 hover:bg-red-700',
    };
    return (
        <button onClick={onClick} disabled={disabled} className={`px-5 py-2 ${colors[color]} text-white rounded-lg font-semibold shadow transition-all disabled:opacity-50 flex items-center space-x-2`}>
            {icon} <span>{label}</span>
        </button>
    );
};

const StatCard = ({ title, stats, value, icon }) => {
    const total = stats?.total ?? value ?? 0;
    const completed = stats?.completed ?? 0;
    const pending = stats?.pending ?? 0;

    return (
        <div className="bg-white rounded-lg shadow-md p-5">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-gray-500">{title}</h3>
                <div className="text-gray-400">{icon}</div>
            </div>
            <p className="text-3xl font-bold mt-2">{total}</p>
            {stats && (
                <div className="flex space-x-4 mt-1 text-xs text-gray-500">
                    <span className="text-green-600">✓ {completed}</span>
                    <span>⏳ {pending}</span>
                </div>
            )}
        </div>
    );
};

const ActivityItem = ({ item }) => (
    <div className="p-4 flex justify-between items-center hover:bg-gray-50">
        <div className="flex items-center space-x-3">
            {item.type === 'collection' ? <Layers className="w-5 h-5 text-purple-500" /> : <Package className="w-5 h-5 text-blue-500" />}
            <div>
                <p className="font-medium">{item.title}</p>
                <p className="text-xs text-gray-500">ID: {item.id}</p>
            </div>
        </div>
        <StatusBadge status={item.status} />
    </div>
);

const StatusBadge = ({ status }) => {
    const styles = {
        pending: 'bg-yellow-100 text-yellow-800',
        processing: 'bg-blue-100 text-blue-800',
        completed: 'bg-green-100 text-green-800',
        failed: 'bg-red-100 text-red-800',
    };
    return (
        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${styles[status] || 'bg-gray-100'}`}>
            {status}
        </span>
    );
};
