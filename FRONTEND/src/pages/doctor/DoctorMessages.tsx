import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { DoctorLayout } from '../../components/layout/DoctorLayout';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { apiClient } from '../../api/client';
import {
  Inbox,
  CheckCircle2,
  Send,
  AlertTriangle,
  Pin,
  Clock,
  ShieldAlert,
  MessageSquare,
  Sparkles,
  X,
  FileQuestion,
  UserCheck,
  Stethoscope,
  Filter,
} from 'lucide-react';

interface TemplateOption {
  label: string;
  category: string;
  title: string;
  content: string;
}

const INQUIRY_TEMPLATES: TemplateOption[] = [
  {
    label: 'Case Diagnostic Review',
    category: 'CLINICAL_QUERY',
    title: 'Diagnostic Consultation on Multi-modal Findings',
    content:
      'Requesting an administrative or senior clinical review regarding diagnostic scan results on patient case. AI model confidence and clinical correlation requires second review.',
  },
  {
    label: 'Model Protocol & Confidence',
    category: 'PROTOCOL_QUESTION',
    title: 'Inquiry regarding model threshold protocol',
    content:
      'Requesting clarification on the institutional protocol for model classification thresholds (e.g. HAM10000 / CheXpert) for borderline clinical indications.',
  },
  {
    label: 'Credential / Registration Update',
    category: 'CREDENTIALS_PROFILE',
    title: 'Medical Council Registration Certificate Update',
    content:
      'Submitting updated State Medical Council registration credentials and licensing details for physician directory compliance.',
  },
  {
    label: 'Technical / Offline Model Help',
    category: 'TECHNICAL_SUPPORT',
    title: 'Technical inquiry regarding local inference pipeline',
    content:
      'Notice regarding local GPU hardware execution and queue processing latency on physician diagnostic workstation.',
  },
];

export const DoctorMessages: React.FC = () => {
  const queryClient = useQueryClient();
  const [replyTextMap, setReplyTextMap] = useState<Record<number, string>>({});

  // Compose Modal State
  const [showComposeModal, setShowComposeModal] = useState(false);
  const [composeTitle, setComposeTitle] = useState('');
  const [composeContent, setComposeContent] = useState('');
  const [composePriority, setComposePriority] = useState<'NORMAL' | 'URGENT'>('NORMAL');
  const [composeCategory, setComposeCategory] = useState<string>('CLINICAL_QUERY');

  // Filter State
  const [activeTab, setActiveTab] = useState<'ALL' | 'FROM_ADMIN' | 'SENT_BY_ME'>('ALL');

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['doctor-messages'],
    queryFn: () => apiClient<any[]>('/api/doctor/messages'),
  });

  const ackMutation = useMutation({
    mutationFn: (id: number) =>
      apiClient(`/api/doctor/messages/${id}/acknowledge`, { method: 'POST' }),
    onSuccess: () => {
      toast.success('Message receipt acknowledged');
      queryClient.invalidateQueries({ queryKey: ['doctor-messages'] });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to acknowledge message'),
  });

  const replyMutation = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      apiClient(`/api/doctor/messages/${id}/reply`, {
        method: 'POST',
        body: JSON.stringify({ reply_text: text }),
      }),
    onSuccess: () => {
      toast.success('Reply submitted to administrator');
      queryClient.invalidateQueries({ queryKey: ['doctor-messages'] });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to submit reply'),
  });

  const sendDoctorMessageMutation = useMutation({
    mutationFn: () =>
      apiClient('/api/doctor/messages', {
        method: 'POST',
        body: JSON.stringify({
          title: composeTitle.trim(),
          content: composeContent.trim(),
          priority: composePriority,
          category: composeCategory,
        }),
      }),
    onSuccess: (data: any) => {
      toast.success(data.message || 'Message sent to Clinical Administration');
      setShowComposeModal(false);
      setComposeTitle('');
      setComposeContent('');
      setComposePriority('NORMAL');
      setComposeCategory('CLINICAL_QUERY');
      queryClient.invalidateQueries({ queryKey: ['doctor-messages'] });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to deliver message to administrator'),
  });

  const handleReplyChange = (id: number, text: string) => {
    setReplyTextMap((prev) => ({ ...prev, [id]: text }));
  };

  const handleApplyTemplate = (tmpl: TemplateOption) => {
    setComposeTitle(tmpl.title);
    setComposeContent(tmpl.content);
    setComposeCategory(tmpl.category);
  };

  const fromAdminCount = useMemo(
    () => messages.filter((m: any) => m.sender_role !== 'doctor').length,
    [messages]
  );

  const sentByMeCount = useMemo(
    () => messages.filter((m: any) => m.sender_role === 'doctor').length,
    [messages]
  );

  const filteredMessages = useMemo(() => {
    if (activeTab === 'FROM_ADMIN') {
      return messages.filter((m: any) => m.sender_role !== 'doctor');
    }
    if (activeTab === 'SENT_BY_ME') {
      return messages.filter((m: any) => m.sender_role === 'doctor');
    }
    return messages;
  }, [messages, activeTab]);

  return (
    <DoctorLayout
      title="Communications & Messages"
      subtitle="Direct communications, protocol advisories, and two-way inquiry channel with Clinical Administration."
      actions={
        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowComposeModal(true)}
          className="gap-2 shadow-sm font-semibold"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Message Administration</span>
        </Button>
      }
    >
      <div className="max-w-4xl space-y-5">
        {/* Navigation / Filter Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-porcelain p-1.5 rounded-[10px] border border-hairline shadow-sm">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setActiveTab('ALL')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-[6px] transition-all flex items-center gap-2 ${activeTab === 'ALL'
                  ? 'bg-cardinal text-porcelain shadow-sm'
                  : 'text-graphite-muted hover:text-graphite hover:bg-snow'
                }`}
            >
              <span>All Messages</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${activeTab === 'ALL' ? 'bg-white/20 text-white' : 'bg-snow border border-hairline'
                  }`}
              >
                {messages.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('FROM_ADMIN')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-[6px] transition-all flex items-center gap-2 ${activeTab === 'FROM_ADMIN'
                  ? 'bg-cardinal text-porcelain shadow-sm'
                  : 'text-graphite-muted hover:text-graphite hover:bg-snow'
                }`}
            >
              <span>From Administration</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${activeTab === 'FROM_ADMIN'
                    ? 'bg-white/20 text-white'
                    : 'bg-snow border border-hairline'
                  }`}
              >
                {fromAdminCount}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('SENT_BY_ME')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-[6px] transition-all flex items-center gap-2 ${activeTab === 'SENT_BY_ME'
                  ? 'bg-cardinal text-porcelain shadow-sm'
                  : 'text-graphite-muted hover:text-graphite hover:bg-snow'
                }`}
            >
              <span>Sent by You</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${activeTab === 'SENT_BY_ME'
                    ? 'bg-white/20 text-white'
                    : 'bg-snow border border-hairline'
                  }`}
              >
                {sentByMeCount}
              </span>
            </button>
          </div>

          <div className="pr-2 hidden sm:flex items-center gap-1.5 text-[11px] text-graphite-muted">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Secure 2-Way Audit Channel</span>
          </div>
        </div>

        {/* Message Cards List */}
        {isLoading ? (
          <div className="py-12 text-center text-xs text-graphite-muted animate-pulse">
            Loading clinical communications...
          </div>
        ) : filteredMessages.length === 0 ? (
          <div className="bg-porcelain border border-hairline rounded-[12px] p-12 text-center text-xs text-graphite-muted shadow-panel space-y-3">
            <Inbox className="w-10 h-10 mx-auto text-graphite-subtle opacity-70" />
            <h3 className="text-sm font-bold text-graphite">
              {activeTab === 'SENT_BY_ME'
                ? 'No messages sent by you yet'
                : activeTab === 'FROM_ADMIN'
                  ? 'No administrative advisories received'
                  : 'Your message box is currently empty'}
            </h3>
            <p className="max-w-md mx-auto text-graphite-muted leading-relaxed">
              Use this clinical channel to communicate directly with administrators regarding case
              findings, diagnostic protocol clarifications, and registration compliance.
            </p>
            <div className="pt-2">
              <Button
                variant="primary"
                size="sm"
                onClick={() => setShowComposeModal(true)}
                className="gap-1.5 shadow-sm"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Compose Message to Administration</span>
              </Button>
            </div>
          </div>
        ) : (
          filteredMessages.map((msg: any) => {
            const isDoctorSender = msg.sender_role === 'doctor';
            const isUrgent = msg.priority === 'URGENT';
            const isAck = msg.status === 'ACKNOWLEDGED';

            // Outbound message sent by Doctor to Admin
            if (isDoctorSender) {
              return (
                <div
                  key={msg.recipient_id}
                  className="bg-porcelain border border-blue-200/80 rounded-[12px] p-5 shadow-panel space-y-3.5 bg-gradient-to-br from-blue-50/20 to-porcelain transition-all"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 border border-blue-300 flex items-center gap-1">
                          <Send className="w-3 h-3" />
                          <span>OUTBOUND TO ADMINISTRATION</span>
                        </span>
                        {msg.msg_type && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono text-graphite-muted bg-snow border border-hairline">
                            {msg.msg_type}
                          </span>
                        )}
                      </div>
                      <h3 className="text-sm font-bold text-graphite pt-0.5">{msg.title}</h3>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${isUrgent
                            ? 'bg-blush text-cardinal border border-red-200'
                            : 'bg-snow text-graphite border border-hairline'
                          }`}
                      >
                        {msg.priority}
                      </span>
                      <span className="text-[11px] text-graphite-muted font-mono">
                        {new Date(msg.created_at).toLocaleDateString()}{' '}
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-graphite leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </p>

                  <div className="pt-3 border-t border-hairline/80 flex items-center justify-between text-[11px] text-graphite-muted">
                    <span className="flex items-center gap-1 text-[#1F7A5C] font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Transmitted & logged in system audit trail</span>
                    </span>
                    <span className="italic">Delivered to Clinical Administration</span>
                  </div>
                </div>
              );
            }

            // Inbound Notice from Admin to Doctor
            return (
              <div
                key={msg.recipient_id}
                className={`bg-porcelain border rounded-[12px] p-5 shadow-panel space-y-3.5 transition-colors ${isUrgent && !isAck ? 'border-cardinal/40 bg-blush/20' : 'border-hairline'
                  }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-graphite/10 text-graphite border border-hairline flex items-center gap-1">
                        <Inbox className="w-3 h-3 text-cardinal" />
                        <span>ADMINISTRATIVE NOTICE</span>
                      </span>
                      {msg.is_pinned && (
                        <span className="inline-flex items-center gap-1 text-cardinal text-[10px] font-semibold">
                          <Pin className="w-3 h-3" />
                          <span>Pinned</span>
                        </span>
                      )}
                    </div>
                    <h3 className="text-sm font-bold text-graphite pt-0.5">{msg.title}</h3>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${isUrgent
                          ? 'bg-blush text-cardinal border border-red-200'
                          : 'bg-snow text-graphite border border-hairline'
                        }`}
                    >
                      {msg.priority}
                    </span>
                    <span className="text-[11px] text-graphite-muted font-mono">
                      {new Date(msg.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-graphite leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                </p>

                {/* Doctor's Previous Reply if already replied */}
                {msg.reply_text && (
                  <div className="p-3 bg-snow rounded-[8px] border border-hairline text-xs space-y-1">
                    <div className="flex items-center justify-between text-[11px] text-graphite-muted">
                      <span className="font-semibold text-graphite flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#1F7A5C]" />
                        <span>Your Reply to Administration:</span>
                      </span>
                      {msg.replied_at && (
                        <span className="text-[10px] font-mono">
                          {new Date(msg.replied_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-cardinal italic font-medium pl-2 border-l-2 border-cardinal">
                      "{msg.reply_text}"
                    </p>
                  </div>
                )}

                {/* Actions & Inline Reply */}
                <div className="pt-3 border-t border-hairline flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 text-xs">
                  <div>
                    {isAck ? (
                      <span className="inline-flex items-center gap-1.5 text-[#1F7A5C] font-semibold text-xs">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>
                          Acknowledged on {new Date(msg.acknowledged_at).toLocaleDateString()}
                        </span>
                      </span>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => ackMutation.mutate(msg.recipient_id)}
                        isLoading={ackMutation.isPending}
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                        Acknowledge notice
                      </Button>
                    )}
                  </div>

                  {!msg.reply_text && (
                    <div className="flex items-center gap-2 flex-1 sm:max-w-md">
                      <input
                        type="text"
                        placeholder="Type reply to administrator..."
                        value={replyTextMap[msg.recipient_id] || ''}
                        onChange={(e) => handleReplyChange(msg.recipient_id, e.target.value)}
                        className="flex-1 px-3 py-1.5 bg-snow rounded-[6px] border border-hairline text-xs focus:border-cardinal focus:bg-porcelain focus:outline-none transition-colors"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          replyMutation.mutate({
                            id: msg.recipient_id,
                            text: replyTextMap[msg.recipient_id] || '',
                          })
                        }
                        disabled={!(replyTextMap[msg.recipient_id] || '').trim()}
                        isLoading={replyMutation.isPending}
                      >
                        <Send className="w-3 h-3 mr-1" />
                        Reply
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Compose Message to Administration Modal */}
      {showComposeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl bg-porcelain rounded-[14px] border border-hairline p-6 shadow-floating space-y-4 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-start justify-between pb-3 border-b border-hairline">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blush flex items-center justify-center text-cardinal shrink-0">
                  <Send className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-graphite">
                    Compose Message to Administration
                  </h3>
                  <p className="text-xs text-graphite-muted">
                    Direct communication with the Clinical & Technical Administrative board.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowComposeModal(false)}
                className="p-1 rounded-[6px] text-graphite-muted hover:text-graphite hover:bg-snow transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Quick Templates */}
            <div>
              <span className="text-[11px] font-semibold text-graphite-muted block mb-1.5">
                Quick Consultation Templates:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {INQUIRY_TEMPLATES.map((tmpl, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleApplyTemplate(tmpl)}
                    className="px-2.5 py-1 text-[11px] font-medium bg-snow hover:bg-blush hover:text-cardinal text-graphite rounded-[6px] border border-hairline transition-colors"
                  >
                    {tmpl.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Form Fields */}
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Category */}
                <div>
                  <label className="font-semibold text-graphite block mb-1">
                    Inquiry Category
                  </label>
                  <select
                    value={composeCategory}
                    onChange={(e) => setComposeCategory(e.target.value)}
                    className="w-full px-3 py-2 bg-snow rounded-[6px] border border-hairline text-xs text-graphite focus:border-cardinal focus:bg-porcelain focus:outline-none"
                  >
                    <option value="CLINICAL_QUERY">Clinical Case / Diagnostic Review</option>
                    <option value="PROTOCOL_QUESTION">Protocol & Model Guidance</option>
                    <option value="CREDENTIALS_PROFILE">Licensing & Registration</option>
                    <option value="TECHNICAL_SUPPORT">Technical & Hardware Support</option>
                    <option value="GENERAL">General Administrative Inquiry</option>
                  </select>
                </div>

                {/* Priority */}
                <div>
                  <label className="font-semibold text-graphite block mb-1">
                    Priority Level
                  </label>
                  <select
                    value={composePriority}
                    onChange={(e) => setComposePriority(e.target.value as 'NORMAL' | 'URGENT')}
                    className="w-full px-3 py-2 bg-snow rounded-[6px] border border-hairline text-xs text-graphite focus:border-cardinal focus:bg-porcelain focus:outline-none"
                  >
                    <option value="NORMAL">Normal Priority</option>
                    <option value="URGENT">Urgent - Immediate Clinical Review</option>
                  </select>
                </div>
              </div>

              {/* Title / Subject */}
              <div>
                <label className="font-semibold text-graphite block mb-1">
                  Subject / Summary <span className="text-cardinal">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Diagnostic Consultation on CheXpert Opacities..."
                  value={composeTitle}
                  onChange={(e) => setComposeTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-snow rounded-[6px] border border-hairline text-xs text-graphite focus:border-cardinal focus:bg-porcelain focus:outline-none"
                />
              </div>

              {/* Content */}
              <div>
                <label className="font-semibold text-graphite block mb-1">
                  Message Content <span className="text-cardinal">*</span>
                </label>
                <textarea
                  rows={5}
                  placeholder="Provide comprehensive details, patient case ID if applicable, or administrative inquiry..."
                  value={composeContent}
                  onChange={(e) => setComposeContent(e.target.value)}
                  className="w-full px-3 py-2 bg-snow rounded-[6px] border border-hairline text-xs text-graphite focus:border-cardinal focus:bg-porcelain focus:outline-none resize-none leading-relaxed"
                />
              </div>
            </div>

            {/* Modal Actions */}
            <div className="pt-3 border-t border-hairline flex items-center justify-end gap-2.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowComposeModal(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => sendDoctorMessageMutation.mutate()}
                isLoading={sendDoctorMessageMutation.isPending}
                disabled={!composeTitle.trim() || !composeContent.trim()}
                className="gap-1.5"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send to Administration</span>
              </Button>
            </div>
          </div>
        </div>
      )}
    </DoctorLayout>
  );
};
