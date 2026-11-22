import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AdminLayout } from '../../components/layout/AdminLayout';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { StatusChip } from '../../components/ui/StatusChip';
import { apiClient } from '../../api/client';
import {
  Send,
  MessageSquare,
  Radio,
  Users,
  CheckCircle2,
  Clock,
  Search,
  Filter,
  ShieldAlert,
  Pin,
  UserCheck,
  Building,
  Hash,
  AlertTriangle,
  Sparkles,
  Inbox,
  Check,
} from 'lucide-react';

export const AdminMessaging: React.FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Tab mode: 'DIRECT' (message each doctor separately) or 'BROADCAST' (system-wide notice)
  const [activeTab, setActiveTab] = useState<'DIRECT' | 'BROADCAST'>('DIRECT');

  // Direct Messaging State
  const initialDocId = searchParams.get('doctorId') ? Number(searchParams.get('doctorId')) : null;
  const [selectedDoctorId, setSelectedDoctorId] = useState<number | null>(initialDocId);
  const [doctorSearch, setDoctorSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'APPROVED' | 'NEEDS_INFO' | 'PENDING'>('ALL');

  // Direct Message Composer State
  const [directTitle, setDirectTitle] = useState('');
  const [directContent, setDirectContent] = useState('');
  const [directPriority, setDirectPriority] = useState('NORMAL');
  const [directIsPinned, setDirectIsPinned] = useState(false);

  // Broadcast Composer State
  const [broadcastTitle, setBroadcastTitle] = useState('');
  const [broadcastContent, setBroadcastContent] = useState('');
  const [broadcastType, setBroadcastType] = useState('ANNOUNCEMENT');
  const [broadcastPriority, setBroadcastPriority] = useState('NORMAL');
  const [broadcastIsPinned, setBroadcastIsPinned] = useState(false);

  // Fetch all registered doctors (any status)
  const { data: allDoctors = [], isLoading: isLoadingDoctors } = useQuery({
    queryKey: ['admin-all-doctors'],
    queryFn: () => apiClient<any[]>('/api/admin/doctors'),
  });

  // Automatically select first doctor if none selected and doctors loaded
  useEffect(() => {
    if (selectedDoctorId === null && allDoctors.length > 0) {
      const urlDocId = searchParams.get('doctorId');
      if (urlDocId && allDoctors.some((d: any) => d.id === Number(urlDocId))) {
        setSelectedDoctorId(Number(urlDocId));
      } else {
        setSelectedDoctorId(allDoctors[0].id);
      }
    }
  }, [allDoctors, searchParams, selectedDoctorId]);

  // Update URL param when selected doctor changes
  const handleSelectDoctor = (id: number) => {
    setSelectedDoctorId(id);
    setSearchParams({ doctorId: String(id) });
  };

  // Filtered doctors list for directory
  const filteredDoctors = useMemo(() => {
    return allDoctors.filter((doc: any) => {
      const matchesSearch =
        doc.full_name?.toLowerCase().includes(doctorSearch.toLowerCase()) ||
        doc.reg_number?.toLowerCase().includes(doctorSearch.toLowerCase()) ||
        doc.specialty?.toLowerCase().includes(doctorSearch.toLowerCase()) ||
        doc.hospital_clinic?.toLowerCase().includes(doctorSearch.toLowerCase());

      const matchesStatus =
        statusFilter === 'ALL' ||
        doc.status === statusFilter ||
        (statusFilter === 'NEEDS_INFO' && doc.status === 'NEEDS_INFO') ||
        (statusFilter === 'PENDING' && (doc.status === 'PENDING' || doc.status === 'NEEDS_INFO'));

      return matchesSearch && matchesStatus;
    });
  }, [allDoctors, doctorSearch, statusFilter]);

  // Selected doctor object
  const currentDoctor = useMemo(() => {
    return allDoctors.find((d: any) => d.id === selectedDoctorId) || null;
  }, [allDoctors, selectedDoctorId]);

  // Fetch specific doctor's conversation thread
  const {
    data: threadData,
    isLoading: isLoadingThread,
    refetch: refetchThread,
  } = useQuery({
    queryKey: ['doctor-message-thread', selectedDoctorId],
    queryFn: () =>
      selectedDoctorId
        ? apiClient<{ doctor: any; messages: any[] }>(`/api/admin/doctors/${selectedDoctorId}/messages`)
        : Promise.resolve({ doctor: null, messages: [] }),
    enabled: !!selectedDoctorId,
  });

  // Fetch all sent messages for broadcast receipts list
  const { data: allSentMessages = [], isLoading: isLoadingMessages } = useQuery({
    queryKey: ['admin-messages'],
    queryFn: () => apiClient<any[]>('/api/admin/messages'),
  });

  // Direct message mutation
  const sendDirectMutation = useMutation({
    mutationFn: () => {
      if (!selectedDoctorId) throw new Error('No doctor selected');
      return apiClient(`/api/admin/doctors/${selectedDoctorId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          title: directTitle.trim() || `Administrative notice to ${currentDoctor?.full_name || 'Practitioner'}`,
          content: directContent.trim(),
          priority: directPriority,
          is_pinned: directIsPinned,
          msg_type: 'INSTRUCTION',
        }),
      });
    },
    onSuccess: (data: any) => {
      toast.success(data.message || 'Direct message delivered');
      setDirectTitle('');
      setDirectContent('');
      refetchThread();
      queryClient.invalidateQueries({ queryKey: ['admin-messages'] });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to deliver direct message'),
  });

  // Broadcast mutation
  const sendBroadcastMutation = useMutation({
    mutationFn: () =>
      apiClient('/api/admin/messages', {
        method: 'POST',
        body: JSON.stringify({
          title: broadcastTitle,
          content: broadcastContent,
          msg_type: broadcastType,
          priority: broadcastPriority,
          doctor_ids: [], // empty = all approved doctors
          is_pinned: broadcastIsPinned,
        }),
      }),
    onSuccess: (data: any) => {
      toast.success(data.message || 'Broadcast announcement dispatched');
      setBroadcastTitle('');
      setBroadcastContent('');
      queryClient.invalidateQueries({ queryKey: ['admin-messages'] });
    },
    onError: (err: any) => toast.error(err.message || 'Failed to dispatch broadcast'),
  });

  const handleSendDirect = (e: React.FormEvent) => {
    e.preventDefault();
    if (!directContent.trim()) {
      toast.error('Message content cannot be blank');
      return;
    }
    sendDirectMutation.mutate();
  };

  const handleSendBroadcast = (e: React.FormEvent) => {
    e.preventDefault();
    if (!broadcastTitle.trim() || !broadcastContent.trim()) {
      toast.error('Subject and message content are required');
      return;
    }
    sendBroadcastMutation.mutate();
  };

  // Quick message templates for instant filling
  const handleApplyTemplate = (subject: string, text: string) => {
    setDirectTitle(subject);
    setDirectContent(text);
  };

  return (
    <AdminLayout
      title="Clinician Messaging"
      subtitle="Communicate directly with individual practitioners or broadcast system-wide advisories."
    >
      {/* Top Navigation Tabs */}
      <div className="flex items-center gap-2 mb-6 border-b border-hairline pb-3">
        <button
          type="button"
          onClick={() => setActiveTab('DIRECT')}
          className={`flex items-center gap-2 px-4 py-2 rounded-[8px] text-xs font-semibold transition-all ${
            activeTab === 'DIRECT'
              ? 'bg-cardinal text-porcelain shadow-sm'
              : 'bg-snow text-graphite hover:bg-blush hover:text-cardinal'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Message Each Doctor Separately</span>
          {allDoctors.length > 0 && (
            <span
              className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] ${
                activeTab === 'DIRECT' ? 'bg-white/20 text-porcelain' : 'bg-hairline text-graphite'
              }`}
            >
              {allDoctors.length}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('BROADCAST')}
          className={`flex items-center gap-2 px-4 py-2 rounded-[8px] text-xs font-semibold transition-all ${
            activeTab === 'BROADCAST'
              ? 'bg-cardinal text-porcelain shadow-sm'
              : 'bg-snow text-graphite hover:bg-blush hover:text-cardinal'
          }`}
        >
          <Radio className="w-4 h-4" />
          <span>Broadcast Announcement</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: DIRECT 1-ON-1 DOCTOR MESSAGING                                    */}
      {/* ========================================================================= */}
      {activeTab === 'DIRECT' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Doctor Directory Selector */}
          <div className="lg:col-span-4 bg-porcelain border border-hairline rounded-[12px] p-4 shadow-panel space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-hairline">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-cardinal" />
                <span className="text-xs font-bold text-graphite">Select Practitioner</span>
              </div>
              <span className="text-[11px] text-graphite-muted">{filteredDoctors.length} available</span>
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-graphite-muted absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Search by name, reg #, specialty..."
                value={doctorSearch}
                onChange={(e) => setDoctorSearch(e.target.value)}
                className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-snow text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
              />
            </div>

            {/* Filter Pills */}
            <div className="flex items-center gap-1.5 text-[10px]">
              {(['ALL', 'APPROVED', 'NEEDS_INFO'] as const).map((st) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setStatusFilter(st)}
                  className={`px-2 py-1 rounded-full font-medium transition-colors ${
                    statusFilter === st
                      ? 'bg-cardinal text-porcelain'
                      : 'bg-snow text-graphite-muted hover:text-graphite'
                  }`}
                >
                  {st === 'ALL' ? 'All' : st === 'APPROVED' ? 'Approved' : 'Needs Info'}
                </button>
              ))}
            </div>

            {/* Doctors Scrollable List */}
            <div className="max-h-[560px] overflow-y-auto space-y-2 pr-1 pt-1">
              {filteredDoctors.length === 0 ? (
                <div className="py-8 text-center text-xs text-graphite-muted">
                  <p>No practitioners match query.</p>
                </div>
              ) : (
                filteredDoctors.map((doc: any) => {
                  const isSelected = selectedDoctorId === doc.id;
                  const initials = doc.full_name
                    ?.replace('Dr.', '')
                    .trim()
                    .split(' ')
                    .map((n: string) => n[0])
                    .join('')
                    .substring(0, 2)
                    .toUpperCase() || 'DR';

                  return (
                    <div
                      key={doc.id}
                      onClick={() => handleSelectDoctor(doc.id)}
                      className={`p-3 rounded-[8px] border cursor-pointer transition-all ${
                        isSelected
                          ? 'border-cardinal bg-blush/30 shadow-sm'
                          : 'border-hairline bg-porcelain hover:bg-snow'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {/* Avatar */}
                        <div
                          className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs shrink-0 ${
                            isSelected
                              ? 'bg-cardinal text-porcelain'
                              : 'bg-snow border border-hairline text-graphite'
                          }`}
                        >
                          {initials}
                        </div>

                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1 mb-0.5">
                            <h4 className="text-xs font-semibold text-graphite truncate">{doc.full_name}</h4>
                            <StatusChip status={doc.status} size="sm" />
                          </div>

                          <div className="text-[11px] text-graphite-muted flex items-center gap-1.5 truncate">
                            <span className="font-medium text-graphite">{doc.specialty}</span>
                            <span>•</span>
                            <span className="font-mono">{doc.reg_number}</span>
                          </div>

                          <div className="text-[10px] text-graphite-muted truncate mt-0.5">
                            {doc.hospital_clinic}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Active 1-on-1 Conversation & Direct Dispatch */}
          <div className="lg:col-span-8 space-y-4">
            {currentDoctor ? (
              <>
                {/* Selected Doctor Header Card */}
                <div className="bg-porcelain border border-hairline rounded-[12px] p-4 shadow-panel flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-full bg-cardinal/10 border border-cardinal/20 text-cardinal flex items-center justify-center font-bold text-sm">
                      {currentDoctor.full_name
                        ?.replace('Dr.', '')
                        .trim()
                        .split(' ')
                        .map((n: string) => n[0])
                        .join('')
                        .substring(0, 2)
                        .toUpperCase() || 'DR'}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-graphite">{currentDoctor.full_name}</h3>
                        <StatusChip status={currentDoctor.status} size="sm" />
                      </div>
                      <div className="text-xs text-graphite-muted flex flex-wrap items-center gap-2 mt-0.5">
                        <span className="font-medium text-graphite">{currentDoctor.specialty}</span>
                        <span>•</span>
                        <span className="font-mono text-[11px]">{currentDoctor.reg_number}</span>
                        <span>•</span>
                        <span>{currentDoctor.hospital_clinic}</span>
                      </div>
                    </div>
                  </div>

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => navigate('/admin/doctors')}
                  >
                    View Doctor Profile
                  </Button>
                </div>

                {/* Conversation Thread History */}
                <div className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-hairline">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-cardinal" />
                      <span className="text-xs font-semibold text-graphite">
                        Communication Thread with {currentDoctor.full_name}
                      </span>
                    </div>
                    <span className="text-[11px] text-graphite-muted">
                      {threadData?.messages?.length || 0} message(s) exchanged
                    </span>
                  </div>

                  {isLoadingThread ? (
                    <div className="py-12 text-center text-xs text-graphite-muted animate-pulse">
                      Loading conversation thread...
                    </div>
                  ) : !threadData?.messages || threadData.messages.length === 0 ? (
                    <div className="py-10 text-center text-xs text-graphite-muted bg-snow/60 rounded-[8px] border border-dashed border-hairline p-6">
                      <Inbox className="w-8 h-8 mx-auto mb-2 text-graphite-muted/50" />
                      <p className="font-medium text-graphite">No direct messages sent to this doctor yet.</p>
                      <p className="mt-1 text-[11px]">
                        Compose a direct message below to send clinical instructions, credential requests, or case advisories.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3.5 max-h-[380px] overflow-y-auto pr-1">
                      {threadData.messages.map((m: any, idx: number) => {
                        const isUrgent = m.priority === 'URGENT';
                        const isAck = m.status === 'ACKNOWLEDGED';
                        const isDoctorSender = m.sender_role === 'doctor';

                        return (
                          <div
                            key={m.message_id || idx}
                            className={`p-4 rounded-[10px] border transition-all ${
                              isDoctorSender
                                ? 'border-blue-200 bg-blue-50/30'
                                : isUrgent
                                ? 'border-cardinal/30 bg-blush/20'
                                : 'border-hairline bg-snow/50'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div>
                                <div className="flex items-center gap-2">
                                  {m.is_pinned && <Pin className="w-3.5 h-3.5 text-cardinal" />}
                                  {isDoctorSender && (
                                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 border border-blue-300">
                                      DOCTOR INQUIRY
                                    </span>
                                  )}
                                  <h4 className="text-xs font-bold text-graphite">{m.title}</h4>
                                </div>
                                <span className="text-[10px] text-graphite-muted">
                                  {isDoctorSender
                                    ? `Received from ${m.sender_name || currentDoctor.full_name} on `
                                    : 'Sent by Admin on '}
                                  {new Date(m.created_at).toLocaleString()}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    isUrgent
                                      ? 'bg-blush text-cardinal border border-red-200'
                                      : 'bg-snow text-graphite border border-hairline'
                                  }`}
                                >
                                  {m.priority}
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                                    isAck
                                      ? 'bg-emerald-50 text-[#1F7A5C] border border-emerald-200'
                                      : 'bg-gray-100 text-graphite-muted border border-gray-200'
                                  }`}
                                >
                                  {m.status}
                                </span>
                              </div>
                            </div>

                            <p className="text-xs text-graphite leading-relaxed whitespace-pre-wrap">
                              {m.content}
                            </p>

                            {/* Doctor Reply Block */}
                            {m.reply_text && (
                              <div className="mt-3 p-3 bg-porcelain rounded-[6px] border border-hairline text-xs space-y-1">
                                <div className="flex items-center justify-between text-[11px] text-graphite-muted">
                                  <span className="font-semibold text-graphite flex items-center gap-1">
                                    <Check className="w-3.5 h-3.5 text-[#1F7A5C]" />
                                    <span>Reply from {currentDoctor.full_name}:</span>
                                  </span>
                                  {m.replied_at && (
                                    <span className="text-[10px]">
                                      {new Date(m.replied_at).toLocaleString()}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-cardinal italic font-medium pl-2 border-l-2 border-cardinal">
                                  "{m.reply_text}"
                                </p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Direct Composer Form */}
                  <div className="pt-4 border-t border-hairline space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-graphite flex items-center gap-1.5">
                        <Send className="w-3.5 h-3.5 text-cardinal" />
                        <span>Send Direct Message to {currentDoctor.full_name}</span>
                      </span>

                      {/* Quick Templates */}
                      <div className="hidden sm:flex items-center gap-1.5 text-[10px]">
                        <span className="text-graphite-muted">Quick template:</span>
                        <button
                          type="button"
                          onClick={() =>
                            handleApplyTemplate(
                              'Request for Updated Medical Council Proof',
                              'Please upload an updated copy of your state medical council registration certificate for compliance verification.'
                            )
                          }
                          className="px-2 py-0.5 bg-snow hover:bg-blush hover:text-cardinal text-graphite rounded border border-hairline transition-colors"
                        >
                          Certificate update
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            handleApplyTemplate(
                              'Diagnostic Narrative Protocol Review',
                              'Please review your narration notes on recent imaging studies to ensure complete anatomical orientation is provided.'
                            )
                          }
                          className="px-2 py-0.5 bg-snow hover:bg-blush hover:text-cardinal text-graphite rounded border border-hairline transition-colors"
                        >
                          Protocol review
                        </button>
                      </div>
                    </div>

                    <form onSubmit={handleSendDirect} className="space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                        <div className="sm:col-span-8">
                          <Input
                            placeholder={`Subject (e.g. Follow-up regarding credential verification)`}
                            value={directTitle}
                            onChange={(e) => setDirectTitle(e.target.value)}
                          />
                        </div>

                        <div className="sm:col-span-4">
                          <select
                            value={directPriority}
                            onChange={(e) => setDirectPriority(e.target.value)}
                            className="w-full px-3 py-2 bg-porcelain rounded-[6px] border border-hairline text-graphite text-xs focus:border-cardinal focus:outline-none"
                          >
                            <option value="NORMAL">Normal Priority</option>
                            <option value="URGENT">Urgent (Requires Ack)</option>
                            <option value="LOW">Low Priority</option>
                          </select>
                        </div>
                      </div>

                      <div>
                        <textarea
                          className="w-full h-24 p-3 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none leading-relaxed"
                          placeholder={`Write your direct message to Dr. ${currentDoctor.full_name} here...`}
                          value={directContent}
                          onChange={(e) => setDirectContent(e.target.value)}
                          required
                        />
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <label className="flex items-center gap-1.5 text-xs text-graphite-muted cursor-pointer">
                          <input
                            type="checkbox"
                            checked={directIsPinned}
                            onChange={(e) => setDirectIsPinned(e.target.checked)}
                            className="rounded text-cardinal"
                          />
                          <span>Pin to top of doctor's inbox</span>
                        </label>

                        <Button
                          type="submit"
                          variant="primary"
                          size="sm"
                          isLoading={sendDirectMutation.isPending}
                        >
                          <Send className="w-3.5 h-3.5 mr-1" />
                          Send to Dr. {currentDoctor.full_name.replace('Dr. ', '')}
                        </Button>
                      </div>
                    </form>
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-porcelain border border-hairline rounded-[12px] p-12 text-center text-xs text-graphite-muted shadow-panel">
                <Users className="w-10 h-10 mx-auto mb-3 text-graphite-muted/40" />
                <h4 className="text-sm font-semibold text-graphite mb-1">No Practitioner Selected</h4>
                <p>Choose a doctor from the directory on the left to start direct messaging.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: BROADCAST ANNOUNCEMENT TO ALL PRACTITIONERS                        */}
      {/* ========================================================================= */}
      {activeTab === 'BROADCAST' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Broadcast Composer */}
          <div className="lg:col-span-5 bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel">
            <h3 className="text-sm font-semibold text-graphite mb-3 flex items-center gap-2">
              <Radio className="w-4 h-4 text-cardinal" />
              <span>Broadcast Announcement</span>
            </h3>

            <form onSubmit={handleSendBroadcast} className="space-y-3.5">
              <Input
                label="Announcement Subject"
                placeholder="e.g. Notice: System maintenance & CheXpert model update..."
                value={broadcastTitle}
                onChange={(e) => setBroadcastTitle(e.target.value)}
                required
              />

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="text-xs font-medium text-graphite mb-1 block">Category</label>
                  <select
                    value={broadcastType}
                    onChange={(e) => setBroadcastType(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-porcelain rounded-[6px] border border-hairline text-graphite text-xs"
                  >
                    <option value="ANNOUNCEMENT">Announcement</option>
                    <option value="INSTRUCTION">Instruction / Decision</option>
                    <option value="SECURITY_ALERT">Security Alert</option>
                    <option value="CASE_RELATED">Case Related</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-medium text-graphite mb-1 block">Priority</label>
                  <select
                    value={broadcastPriority}
                    onChange={(e) => setBroadcastPriority(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-porcelain rounded-[6px] border border-hairline text-graphite text-xs"
                  >
                    <option value="NORMAL">Normal</option>
                    <option value="URGENT">Urgent (Requires Ack)</option>
                    <option value="LOW">Low</option>
                  </select>
                </div>
              </div>

              <div className="p-3 bg-snow rounded-[6px] border border-hairline text-xs">
                <span className="font-semibold text-graphite block mb-1">Target Audience:</span>
                <span className="text-graphite-muted">
                  All active approved practitioners ({allDoctors.filter((d: any) => d.status === 'APPROVED').length} doctors)
                </span>
              </div>

              <div>
                <label className="text-xs font-medium text-graphite mb-1 block">Message Content</label>
                <textarea
                  className="w-full h-28 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal focus:outline-none"
                  placeholder="Type broadcast announcement body here..."
                  value={broadcastContent}
                  onChange={(e) => setBroadcastContent(e.target.value)}
                  required
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                <label className="flex items-center gap-1.5 text-xs text-graphite-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={broadcastIsPinned}
                    onChange={(e) => setBroadcastIsPinned(e.target.checked)}
                    className="rounded text-cardinal"
                  />
                  <span>Pin to top of doctor inbox</span>
                </label>

                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  isLoading={sendBroadcastMutation.isPending}
                >
                  <Send className="w-3.5 h-3.5 mr-1" />
                  Dispatch Broadcast
                </Button>
              </div>
            </form>
          </div>

          {/* Broadcast Sent History & Receipts */}
          <div className="lg:col-span-7 bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel space-y-4">
            <h3 className="text-sm font-semibold text-graphite flex items-center justify-between pb-2 border-b border-hairline">
              <span>Dispatched Broadcasts & Delivery Receipts</span>
              <span className="text-xs text-graphite-muted">{allSentMessages.length} total</span>
            </h3>

            {allSentMessages.length === 0 ? (
              <p className="text-xs text-graphite-muted py-10 text-center">No broadcasts dispatched yet.</p>
            ) : (
              allSentMessages.map((msg: any) => (
                <div key={msg.id} className="p-4 rounded-[8px] border border-hairline bg-snow/50 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="text-sm font-semibold text-graphite block">{msg.title}</span>
                      <span className="text-[11px] text-graphite-muted">
                        {new Date(msg.created_at).toLocaleString()} • {msg.msg_type}
                      </span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        msg.priority === 'URGENT'
                          ? 'bg-blush text-cardinal border border-red-200'
                          : 'bg-gray-100 text-graphite border border-gray-200'
                      }`}
                    >
                      {msg.priority}
                    </span>
                  </div>

                  <p className="text-xs text-graphite leading-relaxed">{msg.content}</p>

                  {/* Receipts table */}
                  <div className="pt-2 border-t border-hairline">
                    <span className="text-[10px] font-semibold text-graphite-muted uppercase block mb-1">
                      Receipts & Acknowledgments:
                    </span>
                    <div className="space-y-1 text-xs max-h-36 overflow-y-auto">
                      {msg.receipts?.map((r: any, idx: number) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between bg-porcelain p-2 rounded border border-hairline"
                        >
                          <span className="font-medium text-graphite">{r.doctor_name}</span>
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-1.5 py-0.2 rounded text-[10px] ${
                                r.status === 'ACKNOWLEDGED'
                                  ? 'bg-emerald-50 text-[#1F7A5C]'
                                  : 'bg-gray-100 text-graphite-muted'
                              }`}
                            >
                              {r.status}
                            </span>
                            {r.reply_text && (
                              <span className="text-[11px] text-cardinal italic">
                                "{r.reply_text}"
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </AdminLayout>
  );
};
