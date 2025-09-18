"use client";

import { useState, useEffect } from 'react';
import axios from 'axios';
import { Package, Folder, CheckCircle, Clock, Play, Plus, Loader2, Terminal } from 'lucide-react';
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card";
import { Progress } from "~/components/ui/progress";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "~/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "~/components/ui/dialog";
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';

interface SystemStatus {
  total_products: number; processed_products: number;
  total_collections: number; processed_collections: number;
  log_messages: string[];
}
interface ShopifyItem { id: number; title: string; }

export default function Home() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [message, setMessage] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [openCommand, setOpenCommand] = useState(false);
  const [products, setProducts] = useState<ShopifyItem[]>([]); // We will need a way to fetch these
  const [collections, setCollections] = useState<ShopifyItem[]>([]); // Same here

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  const fetchStatus = async () => {
    try {
      const { data } = await axios.get(`${apiUrl}/status`);
      setStatus(data);
    } catch (error) { console.error('Error fetching status:', error); }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000); // Faster refresh
    // In a real app, you would fetch products/collections here to populate the manual add dialog
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setIsScanning(true); setMessage('Scanning all products and collections...');
    try {
      const { data } = await axios.post(`${apiUrl}/scan-all`);
      setMessage(data.message);
      await fetchStatus();
    } catch (error: any) { setMessage(error.response?.data?.detail || 'Scan failed.'); }
    finally { setIsScanning(false); }
  };
  
  const handleRequeue = async (item: ShopifyItem, type: 'product' | 'collection') => {
    setMessage(`Re-queuing ${type}: ${item.title}...`);
    try {
        const { data } = await axios.post(`${apiUrl}/requeue-manual`, {
            item_id: item.id, item_type: type, title: item.title
        });
        setMessage(data.message);
    } catch (error: any) { setMessage(error.response?.data?.detail || 'Re-queue failed.');}
    setOpenCommand(false);
  }

  const productProgress = status ? (status.total_products > 0 ? (status.processed_products / status.total_products) * 100 : 0) : 0;
  const collectionProgress = status ? (status.total_collections > 0 ? (status.processed_collections / status.total_collections) * 100 : 0) : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 p-4 sm:p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        <header className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">AI SEO Agent</h1>
            <p className="text-slate-400">Automated Content for Shopify Products & Collections</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setOpenCommand(true)}><Plus className="mr-2 h-4 w-4" /> Manual Re-queue</Button>
            <Button onClick={handleScan} disabled={isScanning}>
              {isScanning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              {isScanning ? 'Scanning...' : 'Scan All'}
            </Button>
          </div>
        </header>

        <main className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader><CardTitle>Processing Status</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-medium text-slate-300">Products</span>
                  <span className="text-sm text-slate-400">{status?.processed_products || 0} / {status?.total_products || 0}</span>
                </div>
                <Progress value={productProgress} />
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-sm font-medium text-slate-300">Collections</span>
                  <span className="text-sm text-slate-400">{status?.processed_collections || 0} / {status?.total_collections || 0}</span>
                </div>
                <Progress value={collectionProgress} />
              </div>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>Live Log</CardTitle></CardHeader>
            <CardContent>
              <div className="bg-slate-900 rounded-md p-4 h-40 overflow-y-auto font-mono text-sm">
                {status?.log_messages?.map((log, i) => <p key={i} className="whitespace-pre-wrap">&raquo; {log}</p>)}
              </div>
            </CardContent>
          </Card>
        </main>
      </div>

      <CommandDialog open={openCommand} onOpenChange={setOpenCommand}>
        <CommandInput placeholder="Search for a product or collection to re-queue..." />
        <CommandList>
          <CommandEmpty>No results found. (Feature requires product/collection fetching)</CommandEmpty>
          <CommandGroup heading="Products">
            {/* In a real app, 'products' state would be populated from a Shopify fetch */}
            <CommandItem onSelect={() => handleRequeue({id: 123, title: "Example Product"}, 'product')}>Example Product</CommandItem>
          </CommandGroup>
          <CommandGroup heading="Collections">
            <CommandItem onSelect={() => handleRequeue({id: 456, title: "Example Collection"}, 'collection')}>Example Collection</CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </div>
  );
}
