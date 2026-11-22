import React, { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { DoctorLayout } from '../../components/layout/DoctorLayout';
import { StatusChip } from '../../components/ui/StatusChip';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ClinicalLogo } from '../../components/ui/ClinicalLogo';
import { apiClient } from '../../api/client';
import {
  UploadCloud,
  FileText,
  Activity,
  Play,
  CheckCircle,
  AlertTriangle,
  Clock,
  Download,
  Printer,
  ChevronRight,
  Shield,
  Layers,
  FileCheck,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Sparkles,
  Sliders,
  Eye,
  RefreshCw,
  QrCode,
  Edit3,
} from 'lucide-react';

export const PatientWorkspace: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>('overview');

  // Imaging Upload States
  const [imagingFile, setImagingFile] = useState<File | null>(null);
  const [bodySite, setBodySite] = useState('');
  const [viewType, setViewType] = useState('PA');
  const [narration, setNarration] = useState('');

  // Text Data States
  const [typedText, setTypedText] = useState('');

  // Running Model / Freeze States
  // 'SKIN' | 'XRAY' | 'MRI' | 'TEXT' | 'LLM' | null
  const [runningModel, setRunningModel] = useState<string | null>(null);

  // Analysis Live SSE States
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStage, setAnalysisStage] = useState('');
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [queuePos, setQueuePos] = useState(0);

  // Before/After comparison sliders map by image key
  const [sliderPositions, setSliderPositions] = useState<Record<string, number>>({});

  // Doctor Decision & Editable PDF States
  const [assessment, setAssessment] = useState('');
  const [plan, setPlan] = useState('');
  const [followUpDate, setFollowUpDate] = useState('');
  const [aiStatus, setAiStatus] = useState<'ACCEPTED' | 'MODIFIED' | 'REJECTED'>('ACCEPTED');
  const [aiStatusReason, setAiStatusReason] = useState('');

  // Editable PDF data states
  const [editAssessment, setEditAssessment] = useState('');
  const [editPlan, setEditPlan] = useState('');
  const [editDetailedAnalysis, setEditDetailedAnalysis] = useState('');
  const [editQuickSummary, setEditQuickSummary] = useState('');
  const [editTriage, setEditTriage] = useState('ROUTINE');
  const [editFollowUpDate, setEditFollowUpDate] = useState('');
  const [isReportInitialized, setIsReportInitialized] = useState(false);

  const { data: caseData, isLoading } = useQuery({
    queryKey: ['case-workspace', id],
    queryFn: () => apiClient<any>(`/api/doctor/cases/${id}`),
    refetchInterval: isAnalyzing ? 3000 : false,
  });

  // Sync initial report states once case data loads
  useEffect(() => {
    if (caseData && !isReportInitialized) {
      setAssessment(caseData.decision?.final_assessment || '');
      setPlan(caseData.decision?.management_plan || '');
      setFollowUpDate(caseData.decision?.follow_up_date || '');
      setAiStatus(caseData.decision?.ai_recommendation_status || 'ACCEPTED');

      setEditAssessment(caseData.decision?.final_assessment || 'Clinical evaluation and diagnostic review completed.');
      setEditPlan(caseData.decision?.management_plan || 'Proceed with prescribed medical regimen and follow-up consultation.');
      setEditDetailedAnalysis(caseData.analysis?.detailed_analysis || '');
      setEditQuickSummary(caseData.analysis?.quick_summary || '');
      setEditTriage(caseData.triage_level || 'ROUTINE');
      setEditFollowUpDate(caseData.decision?.follow_up_date || '');
      setIsReportInitialized(true);
    }
  }, [caseData, isReportInitialized]);

  // Upload Imaging Mutation
  const uploadImagingMutation = useMutation({
    mutationFn: (modality: string) => {
      if (!imagingFile) throw new Error('No image file selected');
      const formData = new FormData();
      formData.append('file', imagingFile);
      formData.append('modality', modality);
      if (modality === 'SKIN') formData.append('body_site', bodySite);
      if (modality === 'XRAY') formData.append('view', viewType);
      formData.append('doctor_narration', narration);
      return apiClient(`/api/doctor/cases/${id}/upload-imaging`, {
        method: 'POST',
        body: formData,
      });
    },
    onSuccess: () => {
      toast.success('Diagnostic imaging uploaded successfully');
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
      setImagingFile(null);
      setNarration('');
    },
    onError: (err: any) => toast.error(err.message || 'Upload failed'),
  });

  // Upload Document Mutation (OCR + Lab Parsing)
  const uploadDocMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('doc_kind', 'report');
      return apiClient(`/api/doctor/cases/${id}/upload-document`, {
        method: 'POST',
        body: formData,
      });
    },
    onSuccess: (data: any) => {
      toast.success(`Extracted ${data.extracted_chars} characters and parsed ${data.labs_count} lab values`);
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
    },
    onError: (err: any) => toast.error(err.message || 'Document processing failed'),
  });

  // Typed Text Document Mutation
  const addTypedDocMutation = useMutation({
    mutationFn: () =>
      apiClient(`/api/doctor/cases/${id}/typed-document`, {
        method: 'POST',
        body: JSON.stringify({ text: typedText, doc_kind: 'report' }),
      }),
    onSuccess: () => {
      toast.success('Clinical note processed and lab values extracted');
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
      setTypedText('');
    },
    onError: (err: any) => toast.error(err.message || 'Processing failed'),
  });

  // Run Specific Individual Model (SKIN, XRAY, MRI, TEXT)
  const runModelMutation = useMutation({
    mutationFn: (modality: string) => {
      setRunningModel(modality);
      return apiClient<any>(`/api/doctor/cases/${id}/run-model/${modality}`, {
        method: 'POST',
      });
    },
    onSuccess: (data: any, modality: string) => {
      setRunningModel(null);
      toast.success(data.message || `${modality} model analysis completed`);
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
    },
    onError: (err: any) => {
      setRunningModel(null);
      toast.error(err.message || 'Model execution failed');
    },
  });

  // Run LLM Multimodal Analysis Mutation (renamed from Run AI Analysis)
  const runLLMMutation = useMutation({
    mutationFn: () => {
      setRunningModel('LLM');
      return apiClient<any>(`/api/doctor/cases/${id}/run-analysis`, {
        method: 'POST',
      });
    },
    onSuccess: (data: any) => {
      toast.info(data.message || 'MedGemma LLM analysis enqueued');
      setIsAnalyzing(true);
      setQueuePos(data.queue_position);
      startEventSource();
    },
    onError: (err: any) => {
      setRunningModel(null);
      toast.error(err.message || 'Could not queue LLM analysis');
    },
  });

  // Doctor Decision Sign-off Mutation
  const decisionMutation = useMutation({
    mutationFn: () =>
      apiClient(`/api/doctor/cases/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify({
          final_assessment: assessment,
          management_plan: plan,
          follow_up_date: followUpDate,
          ai_recommendation_status: aiStatus,
          ai_status_reason: aiStatusReason,
          sign_off: true,
        }),
      }),
    onSuccess: () => {
      toast.success('Clinical decision signed off and locked');
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
    },
    onError: (err: any) => toast.error(err.message || 'Sign-off failed'),
  });

  // Generate / Download Certified PDF Report Mutation (With Editable Overrides)
  const generatePdfMutation = useMutation({
    mutationFn: () =>
      apiClient<{ pdf_url: string; filename: string; version: number }>(`/api/doctor/cases/${id}/generate-pdf`, {
        method: 'POST',
        body: JSON.stringify({
          final_assessment: editAssessment,
          management_plan: editPlan,
          detailed_analysis: editDetailedAnalysis,
          quick_summary: editQuickSummary,
          triage_level: editTriage,
          follow_up_date: editFollowUpDate,
        }),
      }),
    onSuccess: (data) => {
      toast.success(`Certified clinical PDF report compiled (v${data.version})`);
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
      window.open(data.pdf_url, '_blank');
    },
    onError: (err: any) => toast.error(err.message || 'Report generation failed'),
  });

  // Start Server-Sent Events (SSE) Stream
  const startEventSource = () => {
    const es = new EventSource(`/api/doctor/cases/${id}/analysis-stream`);
    es.addEventListener('stage', (e: any) => {
      try {
        const payload = JSON.parse(e.data);
        setAnalysisStage(payload.label || payload.stage);
        setAnalysisProgress(payload.progress || 50);
      } catch {}
    });

    es.addEventListener('queue_update', (e: any) => {
      try {
        const payload = JSON.parse(e.data);
        setQueuePos(payload.queue_position);
      } catch {}
    });

    es.addEventListener('complete', () => {
      setIsAnalyzing(false);
      setRunningModel(null);
      es.close();
      toast.success('MedGemma LLM analysis completed!');
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
    });

    es.addEventListener('error', () => {
      setIsAnalyzing(false);
      setRunningModel(null);
      es.close();
      queryClient.invalidateQueries({ queryKey: ['case-workspace', id] });
    });
  };

  const patient = caseData?.patient || {};
  const vitals = caseData?.vitals || {};
  const uploads = caseData?.uploads || [];
  const documents = caseData?.documents || [];
  const medicines = caseData?.medicines || [];
  const analysis = caseData?.analysis;
  const decision = caseData?.decision;
  const reports = caseData?.reports || [];

  const currentModalityUploads = uploads.filter(
    (u: any) => u.modality === activeTab.toUpperCase()
  );

  // Find model inference result for a given modality
  const getModalityResult = (modalityKey: string) => {
    const runs = analysis?.results?.runs || [];
    return runs.find((r: any) => r.key === modalityKey.toUpperCase()) || null;
  };

  const handleSliderChange = (key: string, val: number) => {
    setSliderPositions((prev) => ({ ...prev, [key]: val }));
  };

  return (
    <DoctorLayout
      title={`Patient Workspace: ${patient.name || 'Loading...'}`}
      subtitle={`MRN: ${patient.patient_code || '-'} • Case: ${caseData?.case_code || '-'}`}
      isLoading={isAnalyzing || runningModel !== null}
      actions={
        <div className="flex items-center gap-2">
          {/* Quick PDF button if report exists */}
          {reports.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('reports')}
            >
              <Download className="w-3.5 h-3.5 mr-1" />
              Download Report (v{reports.length})
            </Button>
          )}

          {/* RENAMED BUTTON: Run LLM Analysis */}
          <Button
            variant="primary"
            size="sm"
            onClick={() => runLLMMutation.mutate()}
            isLoading={runLLMMutation.isPending || isAnalyzing}
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            Run LLM Analysis
          </Button>
        </div>
      }
    >
      {/* ===================================================================== */}
      {/* SCREEN FREEZE MODAL: ONLY LOGO ANIMATION (NO WRITINGS)               */}
      {/* ===================================================================== */}
      {(runningModel !== null || isAnalyzing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/60 backdrop-blur-md p-4 animate-in fade-in duration-200">
          <div className="bg-porcelain/95 rounded-[20px] border border-hairline p-10 shadow-floating flex items-center justify-center">
            <ClinicalLogo size="xl" mode="loop" showText={false} />
          </div>
        </div>
      )}

      {/* Patient Header Summary Bar */}
      <div className="bg-porcelain border border-hairline rounded-[12px] p-4 shadow-panel mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-cardinal/10 border border-cardinal/20 text-cardinal flex items-center justify-center font-bold text-sm">
            {patient.name ? patient.name[0] : 'P'}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-graphite">{patient.name || 'Patient'}</span>
              <StatusChip status={caseData?.triage_level || 'ROUTINE'} size="sm" />
            </div>
            <div className="text-xs text-graphite-muted flex items-center gap-2">
              <span>{patient.age ? `${patient.age} yrs` : '-'}</span>
              <span>•</span>
              <span className="capitalize">{patient.sex || '-'}</span>
              <span>•</span>
              <span>Blood Group: {patient.blood_group || '-'}</span>
              <span>•</span>
              <span className="font-mono text-[11px]">Status: {caseData?.status}</span>
            </div>
          </div>
        </div>

        {/* Vitals Quick-Read */}
        <div className="flex items-center gap-4 text-xs border-l border-hairline pl-4">
          <div>
            <span className="text-[10px] text-graphite-muted uppercase block">Heart Rate</span>
            <span className="font-bold text-graphite tabular-nums">{vitals.heart_rate ? `${vitals.heart_rate} bpm` : '-'}</span>
          </div>
          <div>
            <span className="text-[10px] text-graphite-muted uppercase block">BP</span>
            <span className="font-bold text-graphite tabular-nums">{vitals.blood_pressure || '-'}</span>
          </div>
          <div>
            <span className="text-[10px] text-graphite-muted uppercase block">SpO2</span>
            <span className="font-bold text-graphite tabular-nums">{vitals.spo2 ? `${vitals.spo2}%` : '-'}</span>
          </div>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <div className="flex items-center gap-1 border-b border-hairline mb-6 overflow-x-auto text-xs pb-1">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'skin', label: 'Skin (HAM10000)' },
          { id: 'xray', label: 'Chest X-ray (CheXpert)' },
          { id: 'mri', label: 'Brain MRI (BraTS)' },
          { id: 'text_data', label: 'Text data & Labs' },
          { id: 'medicines', label: 'Medicines' },
          { id: 'decision', label: 'Doctor decision' },
          { id: 'reports', label: 'Reports & PDF Export' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-3 py-2 font-medium transition-all relative whitespace-nowrap rounded-t-[6px] ${
              activeTab === t.id
                ? 'text-cardinal font-semibold bg-blush/30'
                : 'text-graphite-muted hover:text-graphite hover:bg-snow'
            }`}
          >
            {t.label}
            {activeTab === t.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-cardinal" />
            )}
          </button>
        ))}
      </div>

      {/* ===================================================================== */}
      {/* TAB: OVERVIEW                                                         */}
      {/* ===================================================================== */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Clinical Findings & Synthesis Card */}
          {analysis?.status === 'COMPLETED' ? (
            <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel space-y-6">
              <div className="flex items-center justify-between pb-3 border-b border-hairline">
                <div>
                  <h3 className="text-base font-bold text-graphite flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-cardinal" />
                    <span>MedGemma Clinical Multimodal Synthesis</span>
                  </h3>
                  <span className="text-xs text-graphite-muted">
                    Synthesized locally via Ollama medgemma-text pipeline
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setActiveTab('reports')}
                >
                  <Download className="w-3.5 h-3.5 mr-1" />
                  View & Edit Certified Report
                </Button>
              </div>

              {/* Quick Summary Callout */}
              {analysis.quick_summary && (
                <div className="p-4 bg-blush/20 border-l-4 border-cardinal rounded-r-[8px]">
                  <span className="text-xs font-bold text-cardinal uppercase tracking-wider block mb-1">
                    Quick-Read Executive Summary
                  </span>
                  <p className="text-xs text-graphite leading-relaxed">
                    {analysis.quick_summary}
                  </p>
                </div>
              )}

              {/* Detailed Findings Text */}
              {analysis.detailed_analysis && (
                <div>
                  <h4 className="text-xs font-bold text-graphite uppercase tracking-wider mb-2">
                    Structured Clinical Analysis
                  </h4>
                  <div className="p-4 bg-snow rounded-[8px] border border-hairline text-xs text-graphite leading-relaxed whitespace-pre-wrap font-sans">
                    {analysis.detailed_analysis}
                  </div>
                </div>
              )}

              {/* Runs Overview with Attention Heatmaps */}
              <div>
                <h4 className="text-xs font-bold text-graphite uppercase tracking-wider mb-3">
                  Diagnostic Model Findings & Visualizations ({analysis.results?.runs?.length || 0})
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {analysis.results?.runs?.map((r: any, idx: number) => (
                    <div key={idx} className="p-4 bg-snow rounded-[8px] border border-hairline space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-graphite">{r.key} Model Inference</span>
                        <span className="text-[11px] text-graphite-muted font-mono">{r.filename}</span>
                      </div>
                      <p className="text-xs text-graphite whitespace-pre-wrap leading-relaxed">{r.text}</p>

                      {r.figures?.length > 0 && (
                        <div className="mt-2">
                          <span className="text-[10px] font-semibold text-graphite-muted uppercase block mb-1">
                            Attention Heatmap:
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {r.figures.map((fig: string, fi: number) => (
                              <img
                                key={fi}
                                src={fig}
                                alt="Diagnostic visualization"
                                className="rounded-[6px] border border-hairline max-h-48 w-auto shadow-subtle"
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-porcelain border border-hairline rounded-[12px] p-8 text-center text-xs text-graphite-muted shadow-panel">
              <Activity className="w-8 h-8 text-cardinal mx-auto mb-2 opacity-80" />
              <p className="font-medium text-graphite mb-1">Full LLM Analysis Not Yet Executed</p>
              <p className="max-w-[50ch] mx-auto mb-4">
                You can run each model individually in its tab, or click "Run LLM Analysis" to synthesize all findings.
              </p>
              <Button
                variant="primary"
                size="sm"
                onClick={() => runLLMMutation.mutate()}
                isLoading={runLLMMutation.isPending}
              >
                <Sparkles className="w-3.5 h-3.5 mr-1" />
                Run LLM Analysis Now
              </Button>
            </div>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TABS: INDIVIDUAL MODALITIES (SKIN, XRAY, MRI)                         */}
      {/* ===================================================================== */}
      {['skin', 'xray', 'mri'].includes(activeTab) && (
        <div className="space-y-6">
          {/* Modality Header Banner with Dedicated Run Button */}
          <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-hairline">
              <div>
                <h3 className="text-base font-bold text-graphite uppercase">
                  {activeTab === 'skin' && 'HAM10000 Dermatological Classifier'}
                  {activeTab === 'xray' && 'CheXpert Thoracic Pathology Model'}
                  {activeTab === 'mri' && 'BraTS Volumetric Brain Tumor Model'}
                </h3>
                <p className="text-xs text-graphite-muted mt-0.5">
                  {activeTab === 'skin' && '7-class deep convolutional network for pigmented skin lesions and melanoma screening.'}
                  {activeTab === 'xray' && '14-pathology deep radiograph classifier for cardiopulmonary diagnostics.'}
                  {activeTab === 'mri' && 'Multi-sequence volumetric glioma core, edema, and enhancing tumor segmentation.'}
                </p>
              </div>

              {/* INDIVIDUAL RUN BUTTON FOR THIS SPECIFIC MODEL */}
              <Button
                variant="primary"
                size="md"
                onClick={() => runModelMutation.mutate(activeTab.toUpperCase())}
                isLoading={runningModel === activeTab.toUpperCase()}
                disabled={currentModalityUploads.length === 0}
              >
                <Play className="w-3.5 h-3.5 mr-1.5" />
                <span>
                  {activeTab === 'skin' && 'Run Skin Model (HAM10000)'}
                  {activeTab === 'xray' && 'Run Chest X-Ray Model (CheXpert)'}
                  {activeTab === 'mri' && 'Run Brain MRI Model (BraTS)'}
                </span>
              </Button>
            </div>

            {/* Upload Dropzone */}
            <div className="mt-5">
              <div className="p-4 border-2 border-dashed border-hairline rounded-[8px] bg-snow/50 text-center cursor-pointer hover:border-cardinal transition-colors">
                <input
                  type="file"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      setImagingFile(e.target.files[0]);
                    }
                  }}
                  className="hidden"
                  id="imaging-upload"
                  accept={activeTab === 'mri' ? '.npz,.nii,.nii.gz' : '.png,.jpg,.jpeg'}
                />
                <label htmlFor="imaging-upload" className="cursor-pointer block">
                  <UploadCloud className="w-6 h-6 text-cardinal mx-auto mb-1" />
                  <span className="text-xs font-semibold text-graphite block">
                    {imagingFile ? imagingFile.name : `Select or drop ${activeTab.toUpperCase()} scan file`}
                  </span>
                  <span className="text-[11px] text-graphite-muted">
                    {activeTab === 'mri' ? 'Supports NPZ volumetric array files' : 'Supports high-resolution PNG, JPG dermoscopy/radiography'}
                  </span>
                </label>
              </div>

              {/* Upload Parameters Card */}
              {imagingFile && (
                <div className="mt-3 p-4 bg-snow rounded-[8px] border border-hairline space-y-3 text-xs">
                  {activeTab === 'skin' && (
                    <Input
                      label="Anatomical body site"
                      placeholder="e.g. Left upper arm, posterior calf, dorsal foot"
                      value={bodySite}
                      onChange={(e) => setBodySite(e.target.value)}
                    />
                  )}
                  {activeTab === 'xray' && (
                    <div>
                      <label className="text-xs font-medium text-graphite mb-1 block">X-ray projection view</label>
                      <select
                        value={viewType}
                        onChange={(e) => setViewType(e.target.value)}
                        className="w-full px-2.5 py-1.5 bg-porcelain rounded border border-hairline text-xs"
                      >
                        <option value="PA">Posteroanterior (PA)</option>
                        <option value="AP">Anteroposterior (AP)</option>
                        <option value="Lateral">Lateral</option>
                      </select>
                    </div>
                  )}
                  <Input
                    label="Doctor narration / Scan objective"
                    placeholder="e.g. Suspicious pigmented lesion rule-out, border asymmetry"
                    value={narration}
                    onChange={(e) => setNarration(e.target.value)}
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => uploadImagingMutation.mutate(activeTab.toUpperCase())}
                    isLoading={uploadImagingMutation.isPending}
                  >
                    Confirm and upload scan
                  </Button>
                </div>
              )}
            </div>
          </div>

          {/* =================================================================== */}
          {/* MODEL DIAGNOSTIC RESULTS SECTION (IN EACH INDIVIDUAL TAB)           */}
          {/* =================================================================== */}
          {(() => {
            const modResult = getModalityResult(activeTab);
            if (!modResult) {
              return (
                <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-subtle text-center text-xs text-graphite-muted">
                  <Activity className="w-7 h-7 mx-auto mb-2 text-graphite-muted/40" />
                  <p className="font-semibold text-graphite">No {activeTab.toUpperCase()} Inference Run Yet</p>
                  <p className="mt-0.5">
                    {currentModalityUploads.length > 0
                      ? `Click "Run ${activeTab.toUpperCase()} Model" above to execute deep inference on the uploaded scan.`
                      : `Upload a ${activeTab.toUpperCase()} scan file above to run diagnostic inference.`}
                  </p>
                </div>
              );
            }

            const sliderKey = `${activeTab}_slider`;
            const sliderPos = sliderPositions[sliderKey] ?? 50;

            return (
              <div className="bg-porcelain border border-cardinal/20 rounded-[12px] p-6 shadow-panel space-y-5">
                <div className="flex items-center justify-between pb-3 border-b border-hairline">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-[#1F7A5C]" />
                    <h4 className="text-sm font-bold text-graphite">
                      {modResult.key} Model Diagnostic Findings & Heatmaps
                    </h4>
                  </div>
                  {modResult.duration && (
                    <span className="text-[11px] text-graphite-muted font-mono">
                      Inference Time: {modResult.duration}s
                    </span>
                  )}
                </div>

                {/* Descriptive Output Text */}
                <div className="p-4 bg-snow rounded-[8px] border border-hairline">
                  <span className="text-[10px] font-bold text-graphite-muted uppercase tracking-wider block mb-1">
                    Pathological Evaluation Summary
                  </span>
                  <p className="text-xs text-graphite leading-relaxed whitespace-pre-wrap font-sans">
                    {modResult.text}
                  </p>
                </div>

                {/* Class Probabilities Bar Breakdown (if available) */}
                {modResult.result?.probabilities && (
                  <div className="space-y-2">
                    <span className="text-xs font-bold text-graphite block">
                      Differential Diagnosis Probabilities:
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      {Object.entries(modResult.result.probabilities).map(([className, prob]: any) => {
                        const pct = Math.round(Number(prob) * 100);
                        const isHigh = pct >= 50;
                        return (
                          <div key={className} className="p-2.5 bg-snow rounded-[6px] border border-hairline space-y-1">
                            <div className="flex justify-between font-medium">
                              <span className="text-graphite truncate">{className}</span>
                              <span className={isHigh ? 'font-bold text-cardinal' : 'text-graphite-muted'}>
                                {pct}%
                              </span>
                            </div>
                            <div className="w-full h-1.5 bg-porcelain rounded-full overflow-hidden border border-hairline">
                              <div
                                className={`h-full ${isHigh ? 'bg-cardinal' : 'bg-graphite/40'}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Visualizations & Interactive Before/After Heatmap Slider */}
                {modResult.figures?.length > 0 && (
                  <div className="space-y-3 pt-2 border-t border-hairline">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-graphite flex items-center gap-1.5">
                        <Sliders className="w-3.5 h-3.5 text-cardinal" />
                        <span>Interactive Attention Heatmap & Grad-CAM Figures</span>
                      </span>
                      <span className="text-[11px] text-graphite-muted">
                        Split Position: {sliderPos}%
                      </span>
                    </div>

                    {/* Interactive Slider Bar */}
                    <div className="space-y-1 max-w-sm">
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={sliderPos}
                        onChange={(e) => handleSliderChange(sliderKey, Number(e.target.value))}
                        className="w-full accent-cardinal cursor-pointer"
                      />
                      <div className="flex justify-between text-[10px] text-graphite-muted">
                        <span>Original Scan</span>
                        <span>Attention Overlay</span>
                      </div>
                    </div>

                    {/* Rendered Figures Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                      {modResult.figures.map((figUrl: string, idx: number) => (
                        <div key={idx} className="space-y-1 bg-snow p-3 rounded-[8px] border border-hairline">
                          <img
                            src={figUrl}
                            alt="Heatmap figure"
                            className="w-full rounded-[6px] border border-hairline shadow-subtle object-contain max-h-72"
                          />
                          <span className="text-[10px] text-graphite-muted block text-center mt-1">
                            Figure {idx + 1}: Grad-CAM Salience Overlay
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* Existing Uploaded Scans for this Modality */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold text-graphite uppercase tracking-wider">
              Uploaded {activeTab.toUpperCase()} Scans ({currentModalityUploads.length})
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {currentModalityUploads.map((u: any) => (
                <div key={u.id} className="bg-porcelain border border-hairline rounded-[12px] p-4 shadow-subtle space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-graphite">
                    <span>{u.filename}</span>
                    <span className="font-mono text-[10px] text-graphite-muted">
                      {(u.file_size / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </div>
                  {activeTab !== 'mri' && (
                    <img
                      src={u.file_url}
                      alt="Scan preview"
                      className="w-full h-48 object-cover rounded-[6px] border border-hairline"
                    />
                  )}
                  {u.doctor_narration && (
                    <p className="text-xs text-graphite-muted italic">"{u.doctor_narration}"</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB: TEXT DATA & LABS                                                 */}
      {/* ===================================================================== */}
      {activeTab === 'text_data' && (
        <div className="space-y-6">
          {/* Header Banner with Dedicated Run Button */}
          <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-hairline">
              <div>
                <h3 className="text-base font-bold text-graphite">Laboratory Reports & Medical Notes</h3>
                <p className="text-xs text-graphite-muted mt-0.5">
                  OCR document extraction, normal/abnormal reference checks, and vital signs thresholding.
                </p>
              </div>

              {/* INDIVIDUAL RUN BUTTON FOR TEXT & LABS */}
              <Button
                variant="primary"
                size="md"
                onClick={() => runModelMutation.mutate('TEXT')}
                isLoading={runningModel === 'TEXT'}
              >
                <Play className="w-3.5 h-3.5 mr-1.5" />
                Run Text & Lab Analysis
              </Button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-5">
              {/* File upload */}
              <div className="p-4 border-2 border-dashed border-hairline rounded-[8px] bg-snow/50 text-center">
                <input
                  type="file"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      uploadDocMutation.mutate(e.target.files[0]);
                    }
                  }}
                  className="hidden"
                  id="doc-upload"
                  accept=".pdf,.png,.jpg,.jpeg,.txt,.docx"
                />
                <label htmlFor="doc-upload" className="cursor-pointer block">
                  <UploadCloud className="w-6 h-6 text-cardinal mx-auto mb-1" />
                  <span className="text-xs font-semibold text-graphite block">
                    Upload Lab / Prescription Document
                  </span>
                  <span className="text-[11px] text-graphite-muted">
                    Supports PDF, OCR images, DOCX, TXT
                  </span>
                </label>
              </div>

              {/* Paste text */}
              <div className="space-y-2">
                <textarea
                  placeholder="Paste clinical text, lab results, or prescription here..."
                  value={typedText}
                  onChange={(e) => setTypedText(e.target.value)}
                  className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => addTypedDocMutation.mutate()}
                  disabled={!typedText.trim()}
                  isLoading={addTypedDocMutation.isPending}
                >
                  Process pasted text
                </Button>
              </div>
            </div>
          </div>

          {/* Parsed Lab Tables */}
          {documents.map((d: any) => (
            <div key={d.id} className="bg-porcelain border border-hairline rounded-[12px] p-5 shadow-panel space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-hairline">
                <div>
                  <span className="font-bold text-sm text-graphite block">{d.filename}</span>
                  <span className="text-[11px] text-graphite-muted">
                    Method: {d.extraction_method} • Extracted Labs: {d.labs?.length || 0}
                  </span>
                </div>
              </div>

              {d.labs?.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-snow text-graphite-muted text-[10px] uppercase">
                      <tr>
                        <th className="px-3 py-2">Test Name</th>
                        <th className="px-3 py-2">Value</th>
                        <th className="px-3 py-2">Reference</th>
                        <th className="px-3 py-2">Flag</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-hairline">
                      {d.labs.map((l: any, i: number) => (
                        <tr key={i} className="hover:bg-snow/60">
                          <td className="px-3 py-2 font-medium text-graphite">{l.name}</td>
                          <td className="px-3 py-2 tabular-nums">
                            {l.value} {l.unit}
                          </td>
                          <td className="px-3 py-2 text-graphite-muted">{l.ref_range || '-'}</td>
                          <td className="px-3 py-2">
                            {l.is_critical ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blush text-cardinal">
                                CRITICAL {l.flag}
                              </span>
                            ) : l.flag ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700">
                                {l.flag === 'H' ? 'HIGH' : 'LOW'}
                              </span>
                            ) : (
                              <span className="text-graphite-subtle text-[11px]">Normal</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB: MEDICINES                                                        */}
      {/* ===================================================================== */}
      {activeTab === 'medicines' && (
        <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel space-y-4">
          <h3 className="text-base font-bold text-graphite">Patient Medication Regimen</h3>
          {medicines.length === 0 ? (
            <p className="text-xs text-graphite-muted">No medicines logged for this case.</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="bg-snow text-graphite-muted text-[10px] uppercase">
                <tr>
                  <th className="px-3 py-2">Drug Name</th>
                  <th className="px-3 py-2">Dose</th>
                  <th className="px-3 py-2">Frequency</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Indication</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {medicines.map((m: any) => (
                  <tr key={m.id}>
                    <td className="px-3 py-2 font-semibold text-graphite">{m.drug_name}</td>
                    <td className="px-3 py-2">{m.dose}</td>
                    <td className="px-3 py-2">{m.frequency}</td>
                    <td className="px-3 py-2">{m.duration}</td>
                    <td className="px-3 py-2 text-graphite-muted">{m.indication}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB: DOCTOR DECISION                                                  */}
      {/* ===================================================================== */}
      {activeTab === 'decision' && (
        <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel max-w-3xl space-y-4">
          <div className="pb-3 border-b border-hairline">
            <h3 className="text-base font-bold text-graphite">Attending Physician Assessment</h3>
            <p className="text-xs text-graphite-muted">
              Lock your clinical evaluation, management plan, and decision regarding the AI suggestions.
            </p>
          </div>

          <div>
            <label className="text-xs font-semibold text-graphite mb-1.5 block">
              AI Recommendation Action
            </label>
            <div className="flex gap-2">
              {(['ACCEPTED', 'MODIFIED', 'REJECTED'] as const).map((st) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setAiStatus(st)}
                  className={`px-3 py-1.5 rounded-[6px] text-xs font-semibold border transition-colors ${
                    aiStatus === st
                      ? 'bg-blush border-cardinal text-cardinal'
                      : 'bg-snow border-hairline text-graphite-muted'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          <Input
            label="Follow-up scheduled date"
            type="date"
            value={followUpDate}
            onChange={(e) => setFollowUpDate(e.target.value)}
          />

          <div>
            <label className="text-xs font-medium text-graphite mb-1 block">Final Assessment</label>
            <textarea
              className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal"
              placeholder="Enter comprehensive clinical impression..."
              value={assessment}
              onChange={(e) => setAssessment(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs font-medium text-graphite mb-1 block">Management Plan</label>
            <textarea
              className="w-full h-24 p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal"
              placeholder="Prescribed therapies, specialist referral, follow-up..."
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            />
          </div>

          <div className="pt-3 border-t border-hairline flex justify-end">
            <Button
              variant="primary"
              size="md"
              onClick={() => decisionMutation.mutate()}
              isLoading={decisionMutation.isPending}
              disabled={!assessment.trim() || !plan.trim()}
            >
              Sign off & lock clinical decision
            </Button>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB: REPORTS & EDITABLE PDF DOWNLOAD (NEW)                            */}
      {/* ===================================================================== */}
      {activeTab === 'reports' && (
        <div className="space-y-6">
          <div className="bg-porcelain border border-hairline rounded-[12px] p-6 shadow-panel">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-hairline">
              <div>
                <h3 className="text-base font-bold text-graphite flex items-center gap-2">
                  <FileCheck className="w-5 h-5 text-cardinal" />
                  <span>Clinical Report & Certified PDF Export</span>
                </h3>
                <p className="text-xs text-graphite-muted mt-0.5">
                  Review and customize report contents before compiling into a tamper-evident ReportLab PDF.
                </p>
              </div>

              {/* PDF Actions */}
              <div className="flex items-center gap-2">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => generatePdfMutation.mutate()}
                  isLoading={generatePdfMutation.isPending}
                >
                  <Download className="w-4 h-4 mr-1.5" />
                  Download Certified PDF Report
                </Button>
              </div>
            </div>

            {/* Previously Compiled Reports History */}
            {reports.length > 0 && (
              <div className="mt-4 p-3 bg-snow rounded-[8px] border border-hairline text-xs flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-cardinal" />
                  <span className="font-semibold text-graphite">
                    Available PDF Version(s): {reports.length} compiled
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {reports.map((rep: any) => (
                    <a
                      key={rep.id}
                      href={`/api/doctor/cases/${id}/pdf?version=${rep.version}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 bg-porcelain border border-hairline rounded text-[11px] font-semibold text-graphite hover:text-cardinal hover:border-cardinal transition-colors flex items-center gap-1"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download v{rep.version}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Editable PDF Data Editor */}
            <div className="mt-6 space-y-5">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-graphite uppercase tracking-wider flex items-center gap-1.5">
                  <Edit3 className="w-3.5 h-3.5 text-cardinal" />
                  <span>Edit Report Data Before PDF Conversion</span>
                </h4>
                <span className="text-[11px] text-graphite-muted">
                  All adjustments automatically update the generated document
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left Column: Form Fields */}
                <div className="lg:col-span-7 space-y-4">
                  {/* Triage Selector */}
                  <div>
                    <label className="text-xs font-medium text-graphite mb-1 block">
                      Triage Classification Level
                    </label>
                    <select
                      value={editTriage}
                      onChange={(e) => setEditTriage(e.target.value)}
                      className="w-full px-3 py-1.5 bg-snow rounded-[6px] border border-hairline text-xs font-semibold text-graphite focus:border-cardinal"
                    >
                      <option value="ROUTINE">ROUTINE — Standard Monitoring</option>
                      <option value="PRIORITY">PRIORITY — Moderate Acuity Follow-up</option>
                      <option value="URGENT">URGENT — Immediate Intervention Required</option>
                    </select>
                  </div>

                  {/* Final Clinical Assessment */}
                  <div>
                    <label className="text-xs font-medium text-graphite mb-1 block">
                      Attending Physician Assessment (Diagnostic Impression)
                    </label>
                    <textarea
                      rows={3}
                      className="w-full p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal leading-relaxed"
                      placeholder="Doctor's final assessment..."
                      value={editAssessment}
                      onChange={(e) => setEditAssessment(e.target.value)}
                    />
                  </div>

                  {/* Management & Treatment Plan */}
                  <div>
                    <label className="text-xs font-medium text-graphite mb-1 block">
                      Management & Therapeutic Plan
                    </label>
                    <textarea
                      rows={3}
                      className="w-full p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal leading-relaxed"
                      placeholder="Therapeutic management plan..."
                      value={editPlan}
                      onChange={(e) => setEditPlan(e.target.value)}
                    />
                  </div>

                  {/* AI MedGemma Findings Summary */}
                  <div>
                    <label className="text-xs font-medium text-graphite mb-1 block">
                      MedGemma Multimodal AI Narrative Summary
                    </label>
                    <textarea
                      rows={4}
                      className="w-full p-2.5 text-xs bg-porcelain text-graphite rounded-[6px] border border-hairline focus:border-cardinal leading-relaxed font-sans"
                      placeholder="MedGemma narrative findings..."
                      value={editDetailedAnalysis}
                      onChange={(e) => setEditDetailedAnalysis(e.target.value)}
                    />
                  </div>

                  <Input
                    label="Scheduled Follow-up Date"
                    type="date"
                    value={editFollowUpDate}
                    onChange={(e) => setEditFollowUpDate(e.target.value)}
                  />
                </div>

                {/* Right Column: PDF Document Live Letterhead Preview */}
                <div className="lg:col-span-5 bg-snow rounded-[10px] border border-hairline p-5 space-y-4 shadow-subtle">
                  <div className="flex items-center justify-between pb-2 border-b border-hairline">
                    <span className="text-[10px] font-bold text-graphite-muted uppercase tracking-wider">
                      Report Document Layout Preview
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cardinal text-porcelain">
                      Certified
                    </span>
                  </div>

                  {/* Header Preview */}
                  <div className="text-center pb-2 border-b border-hairline">
                    <span className="text-sm font-bold text-graphite block">CLINICALLENS MEDICAL SYSTEM</span>
                    <span className="text-[10px] text-graphite-muted block">
                      Certified Confidential Clinical Diagnostic Dossier
                    </span>
                  </div>

                  {/* Metadata Table Preview */}
                  <div className="text-xs space-y-1.5 text-graphite">
                    <div className="flex justify-between py-0.5 border-b border-hairline/60">
                      <span className="text-graphite-muted">Patient:</span>
                      <span className="font-semibold">{patient.name || '-'}</span>
                    </div>
                    <div className="flex justify-between py-0.5 border-b border-hairline/60">
                      <span className="text-graphite-muted">MRN:</span>
                      <span className="font-mono">{patient.patient_code || '-'}</span>
                    </div>
                    <div className="flex justify-between py-0.5 border-b border-hairline/60">
                      <span className="text-graphite-muted">Case ID:</span>
                      <span className="font-mono">{caseData?.case_code || '-'}</span>
                    </div>
                    <div className="flex justify-between py-0.5 border-b border-hairline/60">
                      <span className="text-graphite-muted">Triage Status:</span>
                      <span className="font-bold text-cardinal">{editTriage}</span>
                    </div>
                    <div className="flex justify-between py-0.5 border-b border-hairline/60">
                      <span className="text-graphite-muted">Attending Doctor:</span>
                      <span className="font-semibold">{caseData?.doctor?.full_name || 'Attending Physician'}</span>
                    </div>
                  </div>

                  {/* Assessment Summary Snippet */}
                  <div className="p-3 bg-porcelain rounded border border-hairline text-xs space-y-1">
                    <span className="text-[10px] font-bold text-graphite-muted uppercase block">
                      Preview Assessment:
                    </span>
                    <p className="text-graphite line-clamp-3 italic">
                      "{editAssessment || 'No assessment entered yet.'}"
                    </p>
                  </div>

                  {/* Sign-off & Download CTA */}
                  <div className="pt-2">
                    <Button
                      variant="primary"
                      size="sm"
                      className="w-full justify-center"
                      onClick={() => generatePdfMutation.mutate()}
                      isLoading={generatePdfMutation.isPending}
                    >
                      <Printer className="w-3.5 h-3.5 mr-1" />
                      Compile & Download PDF
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </DoctorLayout>
  );
};
