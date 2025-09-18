"use client";

import { useState, useEffect } from 'react';
import axios from 'axios';
import { Scan, Pause, Play, Loader, Server, CheckCircle, Clock } from 'lucide-react';

interface SystemStatus {
  is_paused: boolean;
  total_products: number;
  processed_products: number;
  pending_products: number;
}

export default function Home() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [isScanning, setIsScanning] = useState(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const fetchStatus = async () => {
    try {
      setIsLoading(true);
      const { data } = await axios.get(`${apiUrl}/status`);
      setStatus(data);
    } catch (error) {
      setMessage('Error fetching status. Is the backend running?');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // Refresh status every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setIsScanning(true);
    setMessage('Scanning for new products...');
    try {
      const { data } = await axios.post(`${apiUrl}/scan-products`);
      setMessage(data.message);
      await fetchStatus(); // Immediately refresh status after scan
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'An error occurred during scan.');
    } finally {
      setIsScanning(false);
    }
  };
  
  // You would call this endpoint once after deploying to create the table.
  const handleDbSetup = async () => {
    setMessage('Setting up database table...');
    try {
      const { data } = await axios.post(`${apiUrl}/setup-database`);
      setMessage(data.message);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || 'DB setup failed.');
    }
  };

  return (
    <main className="flex min-h-screen bg-gray-900 text-white p-4 sm:p-8 justify-center items-start">
      <div className="w-full max-w-4xl mx-auto space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-cyan-400">AI SEO Agent Dashboard</h1>
          <p className="text-gray-400 mt-2">Live monitoring and control for your automated Shopify SEO.</p>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <StatusCard icon={<Server />} title="Total Products" value={status?.total_products ?? 0} isLoading={isLoading} />
          <StatusCard icon={<CheckCircle />} title="Processed" value={status?.processed_products ?? 0} isLoading={isLoading} />
          <StatusCard icon={<Clock />} title="Pending" value={status?.pending_products ?? 0} isLoading={isLoading} />
        </div>

        {/* Controls */}
        <div className="bg-gray-800 p-6 rounded-lg shadow-lg flex flex-col md:flex-row gap-4 items-center justify-between">
          <h2 className="text-2xl font-bold">System Controls</h2>
          <div className="flex gap-4">
            <button onClick={handleScan} disabled={isScanning} className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-500 text-white font-bold py-2 px-4 rounded-md transition duration-300">
              {isScanning ? <Loader className="animate-spin" /> : <Scan />}
              {isScanning ? 'Scanning...' : 'Scan for New Products'}
            </button>
            <button disabled className="flex items-center gap-2 bg-yellow-600 hover:bg-yellow-700 disabled:bg-gray-500 text-white font-bold py-2 px-4 rounded-md transition duration-300">
              <Pause /> Pause System
            </button>
            {/* One-time setup button for convenience */}
             <button onClick={handleDbSetup} className="bg-indigo-600 text-white p-2 rounded">DB Setup</button>
          </div>
        </div>
        
        {/* Log/Message Area */}
        {message && (
          <div className="bg-gray-800 p-4 rounded-lg shadow-lg">
            <h3 className="font-bold text-gray-300">Last Message:</h3>
            <p className="font-mono text-cyan-300 mt-2">{message}</p>
          </div>
        )}
      </div>
    </main>
  );
}

// A reusable card component
const StatusCard = ({ icon, title, value, isLoading }: { icon: React.ReactNode, title: string, value: number, isLoading: boolean }) => (
  <div className="bg-gray-800 p-6 rounded-lg shadow-lg flex items-center gap-4">
    <div className="text-cyan-400">{icon}</div>
    <div>
      <p className="text-gray-400">{title}</p>
      {isLoading ? <div className="h-8 w-16 bg-gray-700 rounded animate-pulse"></div> : <p className="text-3xl font-bold">{value.toLocaleString()}</p>}
    </div>
  </div>
);
