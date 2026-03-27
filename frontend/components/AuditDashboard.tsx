// frontend/components/AuditDashboard.tsx
'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, AlertTriangle, CheckCircle, XCircle, Clock,
  TrendingUp, TrendingDown, Minus, Eye, Download,
  RefreshCw, Calendar, Filter, Search, ChevronRight,
  Shield, Gauge, Globe, Link, FileText, Image,
  Zap, Smartphone, Lock, ArrowUp, ArrowDown
} from 'lucide-react';
import IntegrationSetupChecklist from './IntegrationSetupChecklist';

interface AuditData {
  audit: {
    id: number;
    health_score: number;
    previous_score: number;
    score_change: number;
    technical_score: number;
    content_score: number;
    performance_score: number;
    mobile_score: number;
    security_score: number;
    total_issues: number;
    critical_issues: number;
    errors: number;
    warnings: number;
    notices: number;
    new_issues: number;
    fixed_issues: number;
    audit_date: string;
  };
  issues: Issue[];
  recommendations: Recommendation[];
}

interface Issue {
  id: number;
  issue_type: string;
  severity: string;
  category: string;
  title: string;
  description?: string;
  affected_pages: string[];
  how_to_fix: string;
  estimated_impact: number;
  effort_required: string;
  implementation_status?: string;
  first_detected?: string;
  occurrences?: number;
}

interface Recommendation {
  id: number;
  priority: number;
  category?: string;
  title: string;
  description: string;
  expected_impact: string;
  implementation_complexity: string;
  estimated_traffic_gain: number;
}

export default function AuditDashboard({ websiteId }: { websiteId: number }) {
  const [auditData, setAuditData] = useState<AuditData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedSeverity, setSelectedSeverity] = useState('all');
  const [isRunningAudit, setIsRunningAudit] = useState(false);
  const [expandedIssue, setExpandedIssue] = useState<number | null>(null);
  const [siteType, setSiteType] = useState('custom');

  const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

  useEffect(() => {
    fetchLatestAudit();
    fetchWebsiteInfo();
  }, [websiteId]);

  const fetchWebsiteInfo = async () => {
    try {
      const response = await fetch(`${API_URL}/websites`);
      if (response.ok) {
        const websites = await response.json();
        const current = websites.find((w: any) => w.id === websiteId);
        if (current) {
          setSiteType(current.site_type || 'custom');
        }
      }
    } catch (error) {
      console.error('Error fetching website info:', error);
    }
  };

  const fetchLatestAudit = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/audit/${websiteId}`);
      if (response.ok) {
        const data = await response.json();
        setAuditData(data);
      }
    } catch (error) {
      console.error('Error fetching audit:', error);
    } finally {
      setLoading(false);
    }
  };

  const runAudit = async () => {
    setIsRunningAudit(true);
    try {
      await fetch(`${API_URL}/api/audit/${websiteId}/start`, { method: 'POST' });
      // Poll for completion
      setTimeout(async () => {
        await fetchLatestAudit();
        setIsRunningAudit(false);
      }, 5000);
    } catch (error) {
      console.error('Error starting audit:', error);
      setIsRunningAudit(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-400';
    if (score >= 70) return 'text-yellow-400';
    if (score >= 50) return 'text-orange-400';
    return 'text-red-400';
  };

  const getSeverityColor = (severity: string) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 'error': return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
      case 'warning': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'notice': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category?.toLowerCase()) {
      case 'technical': return <Globe className="w-4 h-4" />;
      case 'content': return <FileText className="w-4 h-4" />;
      case 'performance': return <Gauge className="w-4 h-4" />;
      case 'mobile': return <Smartphone className="w-4 h-4" />;
      case 'security': return <Lock className="w-4 h-4" />;
      case 'accessibility': return <Eye className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };

  const filteredIssues = auditData?.issues?.filter(issue => {
    if (selectedCategory !== 'all' && issue.category?.toLowerCase() !== selectedCategory) return false;
    if (selectedSeverity !== 'all' && issue.severity?.toLowerCase() !== selectedSeverity) return false;
    return true;
  }) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Integration Setup Checklist — shows only when platforms are not yet connected */}
      <IntegrationSetupChecklist
        websiteId={websiteId}
        siteType={siteType}
        onIntegrationChange={fetchLatestAudit}
      />

      {/* Header with Health Score */}
      {auditData && (
        <>
          <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 backdrop-blur-md rounded-2xl p-6 border border-white/20">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold text-white mb-2">Site Health Audit</h2>
                <p className="text-purple-300">
                  Last audit: {new Date(auditData.audit.audit_date).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={runAudit}
                disabled={isRunningAudit}
                className="bg-purple-500 text-white px-4 py-2 rounded-lg font-medium hover:bg-purple-600 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {isRunningAudit ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Running Audit...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    Run New Audit
                  </>
                )}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Overall Health Score */}
              <div className="text-center">
                <div className="relative inline-flex items-center justify-center">
                  <svg className="w-32 h-32 transform -rotate-90">
                    <circle
                      cx="64" cy="64" r="56"
                      stroke="rgba(255, 255, 255, 0.1)"
                      strokeWidth="12" fill="none"
                    />
                    <circle
                      cx="64" cy="64" r="56"
                      stroke="url(#scoreGradient)"
                      strokeWidth="12" fill="none"
                      strokeDasharray={`${(auditData.audit.health_score / 100) * 351.86} 351.86`}
                      strokeLinecap="round"
                    />
                    <defs>
                      <linearGradient id="scoreGradient">
                        <stop offset="0%" stopColor="#a855f7" />
                        <stop offset="100%" stopColor="#ec4899" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute">
                    <p className={`text-4xl font-bold ${getScoreColor(auditData.audit.health_score)}`}>
                      {Math.round(auditData.audit.health_score)}
                    </p>
                    <p className="text-xs text-gray-400">Health Score</p>
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-center gap-2">
                  {auditData.audit.score_change > 0 ? (
                    <ArrowUp className="w-4 h-4 text-green-400" />
                  ) : auditData.audit.score_change < 0 ? (
                    <ArrowDown className="w-4 h-4 text-red-400" />
                  ) : (
                    <Minus className="w-4 h-4 text-gray-400" />
                  )}
                  <span className={
                    auditData.audit.score_change > 0 ? 'text-green-400' :
                    auditData.audit.score_change < 0 ? 'text-red-400' : 'text-gray-400'
                  }>
                    {Math.abs(auditData.audit.score_change)} points
                  </span>
                </div>
              </div>

              {/* Issue Summary */}
              <div className="space-y-3">
                <h3 className="text-white font-medium mb-2">Issue Breakdown</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-red-400 flex items-center gap-2">
                      <XCircle className="w-4 h-4" /> Critical
                    </span>
                    <span className="text-white font-bold">{auditData.audit.critical_issues}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-orange-400 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" /> Errors
                    </span>
                    <span className="text-white font-bold">{auditData.audit.errors}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-yellow-400 flex items-center gap-2">
                      <Clock className="w-4 h-4" /> Warnings
                    </span>
                    <span className="text-white font-bold">{auditData.audit.warnings}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-blue-400 flex items-center gap-2">
                      <Eye className="w-4 h-4" /> Notices
                    </span>
                    <span className="text-white font-bold">{auditData.audit.notices}</span>
                  </div>
                </div>
              </div>

              {/* Quick Stats */}
              <div className="space-y-3">
                <h3 className="text-white font-medium mb-2">Changes Since Last Audit</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-purple-300">Total Issues</span>
                    <span className="text-white font-bold">{auditData.audit.total_issues}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-purple-300">New Issues</span>
                    <span className="text-white font-bold">+{auditData.audit.new_issues}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-purple-300">Fixed Issues</span>
                    <span className="text-green-400 font-bold">{auditData.audit.fixed_issues}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Category Scores */}
            <div className="grid grid-cols-5 gap-4 mt-6">
              {[
                { label: 'Technical', score: auditData.audit.technical_score, icon: Globe },
                { label: 'Content', score: auditData.audit.content_score, icon: FileText },
                { label: 'Performance', score: auditData.audit.performance_score, icon: Gauge },
                { label: 'Mobile', score: auditData.audit.mobile_score, icon: Smartphone },
                { label: 'Security', score: auditData.audit.security_score, icon: Lock }
              ].map((category) => (
                <div key={category.label} className="bg-white/10 rounded-xl p-4 text-center">
                  <category.icon className="w-5 h-5 text-purple-400 mx-auto mb-2" />
                  <p className="text-xs text-gray-400 mb-1">{category.label}</p>
                  <p className={`text-2xl font-bold ${getScoreColor(category.score)}`}>
                    {Math.round(category.score)}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Filters */}
          <div className="bg-white/10 backdrop-blur-md rounded-2xl p-4 border border-white/20">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-purple-400" />
                <span className="text-white font-medium text-sm">Filters:</span>
              </div>

              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="bg-white/10 text-white border border-white/20 rounded-lg px-3 py-1.5 text-sm"
              >
                <option value="all">All Categories</option>
                <option value="technical">Technical</option>
                <option value="content">Content</option>
                <option value="performance">Performance</option>
                <option value="mobile">Mobile</option>
                <option value="security">Security</option>
                <option value="accessibility">Accessibility</option>
              </select>

              <select
                value={selectedSeverity}
                onChange={(e) => setSelectedSeverity(e.target.value)}
                className="bg-white/10 text-white border border-white/20 rounded-lg px-3 py-1.5 text-sm"
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="error">Errors</option>
                <option value="warning">Warnings</option>
                <option value="notice">Notices</option>
              </select>

              <div className="ml-auto text-white text-sm">
                Showing {filteredIssues.length} of {auditData.issues?.length || 0} issues
              </div>
            </div>
          </div>

          {/* Issues List */}
          <div className="space-y-3">
            <AnimatePresence>
              {filteredIssues.map((issue) => (
                <motion.div
                  key={issue.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="bg-white/10 backdrop-blur-md rounded-xl border border-white/20 overflow-hidden"
                >
                  <div
                    className="p-4 cursor-pointer hover:bg-white/5 transition-all"
                    onClick={() => setExpandedIssue(expandedIssue === issue.id ? null : issue.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-3">
                        <div className={`p-2 rounded-lg border ${getSeverityColor(issue.severity)}`}>
                          {getCategoryIcon(issue.category)}
                        </div>
                        <div className="flex-1">
                          <h4 className="text-white font-medium">{issue.title}</h4>
                          {issue.description && (
                            <p className="text-purple-300 text-sm mt-1">{issue.description}</p>
                          )}
                          <div className="flex items-center gap-4 mt-2">
                            <span className="text-xs text-gray-400">
                              Affects {issue.affected_pages?.length || 0} page{(issue.affected_pages?.length || 0) !== 1 ? 's' : ''}
                            </span>
                            <span className="text-xs text-gray-400">
                              Impact: {issue.estimated_impact}%
                            </span>
                            <span className="text-xs text-gray-400">
                              Effort: {issue.effort_required}
                            </span>
                          </div>
                        </div>
                      </div>
                      <ChevronRight
                        className={`w-5 h-5 text-gray-400 transition-transform ${
                          expandedIssue === issue.id ? 'rotate-90' : ''
                        }`}
                      />
                    </div>
                  </div>

                  {expandedIssue === issue.id && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: 'auto' }}
                      exit={{ height: 0 }}
                      className="border-t border-white/10"
                    >
                      <div className="p-4 space-y-4">
                        <div>
                          <h5 className="text-white font-medium mb-2">How to Fix:</h5>
                          <p className="text-purple-300 text-sm">{issue.how_to_fix}</p>
                        </div>

                        {issue.affected_pages && issue.affected_pages.length > 0 && (
                          <div>
                            <h5 className="text-white font-medium mb-2">Affected Pages:</h5>
                            <div className="space-y-1">
                              {issue.affected_pages.slice(0, 5).map((page, idx) => (
                                <div key={idx} className="flex items-center gap-2">
                                  <Link className="w-3 h-3 text-gray-400" />
                                  <a
                                    href={page}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-purple-300 text-sm hover:text-purple-400 truncate"
                                  >
                                    {page}
                                  </a>
                                </div>
                              ))}
                              {issue.affected_pages.length > 5 && (
                                <p className="text-gray-400 text-sm">
                                  ...and {issue.affected_pages.length - 5} more
                                </p>
                              )}
                            </div>
                          </div>
                        )}

                        <div className="flex gap-2">
                          <button className="bg-purple-500/20 text-purple-400 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-purple-500/30 transition-all">
                            Create Fix
                          </button>
                          <button className="bg-white/10 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-all">
                            Mark as Fixed
                          </button>
                          <button className="bg-white/10 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-all">
                            Ignore
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {filteredIssues.length === 0 && (
              <div className="text-center py-12 bg-white/5 rounded-xl">
                <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
                <p className="text-white font-medium">No issues found</p>
                <p className="text-gray-400 text-sm mt-1">
                  {selectedCategory !== 'all' || selectedSeverity !== 'all'
                    ? 'Try adjusting your filters'
                    : 'Your site looks great!'}
                </p>
              </div>
            )}
          </div>

          {/* Recommendations */}
          {auditData.recommendations && auditData.recommendations.length > 0 && (
            <div className="bg-white/10 backdrop-blur-md rounded-2xl p-6 border border-white/20">
              <h3 className="text-xl font-bold text-white mb-4">Top Recommendations</h3>
              <div className="space-y-3">
                {auditData.recommendations.slice(0, 5).map((rec) => (
                  <div key={rec.id} className="flex items-start gap-3 p-3 bg-white/5 rounded-lg">
                    <span className="flex items-center justify-center w-8 h-8 bg-purple-500/20 text-purple-400 rounded-full font-bold text-sm shrink-0">
                      {rec.priority}
                    </span>
                    <div className="flex-1">
                      <h4 className="text-white font-medium">{rec.title}</h4>
                      <p className="text-purple-300 text-sm mt-1">{rec.description}</p>
                      <div className="flex items-center gap-4 mt-2">
                        <span className="text-xs text-gray-400">
                          Impact: {rec.expected_impact}
                        </span>
                        <span className="text-xs text-gray-400">
                          Complexity: {rec.implementation_complexity}
                        </span>
                        {rec.estimated_traffic_gain > 0 && (
                          <span className="text-xs text-green-400">
                            +{rec.estimated_traffic_gain} visitors/mo
                          </span>
                        )}
                      </div>
                    </div>
                    <button className="bg-purple-500/20 text-purple-400 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-purple-500/30 transition-all shrink-0">
                      Implement
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
