'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import { RefreshCw, Package, Clock, CheckCircle, PlayCircle, Search } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Dashboard() {
  const [stats, setStats] = useState({
    total_products: 0,
    completed: 0,
    pending: 0,
    in_queue: 0,
    new_today: 0,
    processed_today: 0,
    completion_rate: 0
  });
  
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    fetchStats();
    fetchProducts();
    const interval = setInterval(() => {
      fetchStats();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const fetchProducts = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/products?limit=10`);
      setProducts(response.data.products);
      setLoading(false);
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
    }
  };

  const triggerScan = async () => {
    setProcessing(true);
    try {
      await axios.post(`${API_URL}/api/scan`);
      setTimeout(() => {
        fetchStats();
        fetchProducts();
        setProcessing(false);
      }, 2000);
    } catch (error) {
      setProcessing(false);
    }
  };

  const processQueue = async () => {
    setProcessing(true);
    try {
      await axios.post(`${API_URL}/api/process-queue`);
      setTimeout(() => {
        fetchStats();
        setProcessing(false);
      }, 2000);
    } catch (error) {
      setProcessing(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">SEO Content Agent</h1>
        <p className="text-gray-600 mt-2">AI-powered content generation</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Total Products</p>
              <p className="text-2xl font-semibold mt-1">{stats.total_products}</p>
            </div>
            <Package className="w-5 h-5 text-blue-600" />
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Completed</p>
              <p className="text-2xl font-semibold mt-1">{stats.completed}</p>
            </div>
            <CheckCircle className="w-5 h-5 text-green-600" />
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">In Queue</p>
              <p className="text-2xl font-semibold mt-1">{stats.in_queue}</p>
            </div>
            <Clock className="w-5 h-5 text-yellow-600" />
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Completion</p>
              <p className="text-2xl font-semibold mt-1">{stats.completion_rate}%</p>
            </div>
            <RefreshCw className="w-5 h-5 text-purple-600" />
          </div>
        </div>
      </div>

      <div className="flex gap-4 mb-8">
        <button
          onClick={triggerScan}
          disabled={processing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <Search className="w-4 h-4" />
          Scan Products
        </button>
        
        <button
          onClick={processQueue}
          disabled={processing}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          <PlayCircle className="w-4 h-4" />
          Process Queue
        </button>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">Recent Products</h2>
        </div>
        <div className="divide-y">
          {loading ? (
            <div className="p-6 text-center text-gray-500">Loading...</div>
          ) : products.length === 0 ? (
            <div className="p-6 text-center text-gray-500">No products found</div>
          ) : (
            products.map((product: any) => (
              <div key={product.id} className="p-4">
                <h3 className="font-medium">{product.title}</h3>
                <p className="text-sm text-gray-500 mt-1">
                  {product.product_type} • {product.vendor}
                </p>
                <span className={`inline-block px-2 py-1 text-xs rounded-full mt-2 ${
                  product.status === 'completed' ? 'bg-green-100 text-green-800' :
                  product.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                  'bg-yellow-100 text-yellow-800'
                }`}>
                  {product.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
