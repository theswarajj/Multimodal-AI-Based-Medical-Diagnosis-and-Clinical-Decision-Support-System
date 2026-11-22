import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { DoctorLayout } from '../../components/layout/DoctorLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { apiClient, ApiError } from '../../api/client';
import {
  User,
  HeartPulse,
  Stethoscope,
  Pill,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react';

const patientSchema = z.object({
  // Step 1: Basic Details
  name: z.string().min(2, 'Patient full name is required'),
  dob: z.string().optional(),
  age: z.coerce.number().min(0).max(120, 'Please enter a valid age'),
  sex: z.enum(['Male', 'Female', 'Other']),
  blood_group: z.string().optional(),
  height_cm: z.coerce.number().optional(),
  weight_kg: z.coerce.number().optional(),
  phone: z.string().optional(),
  consent_confirmed: z.literal(true, {
    errorMap: () => ({ message: 'Patient consent must be confirmed' }),
  }),

  // Step 2: Vitals
  temp_c: z.coerce.number().optional(),
  hr: z.coerce.number().optional(),
  bp_sys: z.coerce.number().optional(),
  bp_dia: z.coerce.number().optional(),
  spo2: z.coerce.number().optional(),
  rr: z.coerce.number().optional(),

  // Step 3: History
  chief_complaint: z.string().optional(),
  onset_duration: z.string().optional(),
  associated_symptoms: z.string().optional(),
  past_history: z.string().optional(),
  family_history: z.string().optional(),
  allergies: z.string().optional(),
  lifestyle: z.string().optional(),
  doctor_question: z.string().optional(),

  // Modality-specific answers
  skin_site: z.string().optional(),
  skin_change: z.string().optional(),
  skin_sun: z.string().optional(),
  chest_cough: z.string().optional(),
  chest_fever: z.string().optional(),
  chest_tb: z.string().optional(),
  brain_headache: z.string().optional(),
  brain_seizures: z.string().optional(),
  brain_deficits: z.string().optional(),
});

type PatientFormData = z.infer<typeof patientSchema>;

const STEPS = [
  { id: 1, title: 'Basic details', icon: User },
  { id: 2, title: 'Vital signs', icon: HeartPulse },
  { id: 3, title: 'Clinical history', icon: Stethoscope },
  { id: 4, title: 'Medicines', icon: Pill },
  { id: 5, title: 'Review & save', icon: CheckCircle2 },
];

export const PatientCreateStepper: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedScanType, setSelectedScanType] = useState<string>('NONE');

  // Step 4 Medicines State
  const [medicines, setMedicines] = useState<
    { drug_name: string; dose: string; frequency: string; duration: string; since_when: string; indication: string }[]
  >([
    { drug_name: '', dose: '', frequency: '', duration: '', since_when: '', indication: '' }
  ]);

  const {
    register,
    handleSubmit,
    trigger,
    watch,
    setValue,
    formState: { errors },
  } = useForm<PatientFormData>({
    resolver: zodResolver(patientSchema),
    defaultValues: {
      sex: 'Male',
      consent_confirmed: true,
      age: 45,
    },
  });

  const formValues = watch();

  const handleAddMedicineRow = () => {
    setMedicines((prev) => [
      ...prev,
      { drug_name: '', dose: '', frequency: '', duration: '', since_when: '', indication: '' },
    ]);
  };

  const handleRemoveMedicineRow = (index: number) => {
    setMedicines((prev) => prev.filter((_, i) => i !== index));
  };

  const handleMedicineChange = (index: number, field: string, value: string) => {
    setMedicines((prev) => {
      const updated = [...prev];
      (updated[index] as any)[field] = value;
      return updated;
    });
  };

  const handleNextStep = async () => {
    let valid = false;
    if (currentStep === 1) {
      valid = await trigger(['name', 'age', 'sex', 'consent_confirmed']);
    } else if (currentStep === 2) {
      // Vitals are optional but if entered should be valid
      valid = true;
    } else if (currentStep === 3) {
      valid = true;
    } else if (currentStep === 4) {
      valid = true;
    }

    if (valid) {
      setCurrentStep((prev) => Math.min(prev + 1, 5));
    }
  };

  const onSubmit = async (data: PatientFormData) => {
    setIsLoading(true);
    try {
      // Modality questions mapping
      const modalityQuestions: Record<string, any> = {};
      if (selectedScanType === 'SKIN') {
        modalityQuestions['SKIN'] = {
          lesion_site: data.skin_site,
          lesion_change: data.skin_change,
          sun_history: data.skin_sun,
        };
      } else if (selectedScanType === 'XRAY') {
        modalityQuestions['XRAY'] = {
          resp_symptoms: `${data.chest_cough || ''} ${data.chest_fever || ''}`.trim(),
          exposure: data.chest_tb,
        };
      } else if (selectedScanType === 'MRI') {
        modalityQuestions['MRI'] = {
          neuro: `${data.brain_headache || ''} ${data.brain_seizures || ''} ${data.brain_deficits || ''}`.trim(),
          prior_tx: '',
        };
      }

      // Filter empty medicines
      const validMeds = medicines.filter((m) => m.drug_name.trim() !== '');

      const payload = {
        name: data.name,
        dob: data.dob,
        age: data.age,
        sex: data.sex,
        blood_group: data.blood_group,
        height_cm: data.height_cm,
        weight_kg: data.weight_kg,
        phone: data.phone,
        consent_confirmed: true,
        temp_c: data.temp_c,
        hr: data.hr,
        bp_sys: data.bp_sys,
        bp_dia: data.bp_dia,
        spo2: data.spo2,
        rr: data.rr,
        chief_complaint: data.chief_complaint,
        onset_duration: data.onset_duration,
        associated_symptoms: data.associated_symptoms,
        past_history: data.past_history,
        family_history: data.family_history,
        allergies: data.allergies,
        lifestyle: data.lifestyle,
        modality_questions: modalityQuestions,
        doctor_question: data.doctor_question,
        medicines: validMeds,
      };

      const res = await apiClient<{ status: string; patient: { case_id: number; case_code: string } }>(
        '/api/doctor/patients',
        {
          method: 'POST',
          body: JSON.stringify(payload),
        }
      );

      toast.success('Patient record initialized with clinical case');
      navigate(`/doctor/cases/${res.patient.case_id}`);
    } catch (err: any) {
      toast.error(err.message || 'Failed to create patient record');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <DoctorLayout
      title="Create Patient Profile"
      subtitle="Complete sequential medical intake: demographics, vital signs, clinical anamnesis, and medication history."
    >
      {/* 5-Step Progress Indicator */}
      <nav aria-label="Progress" className="mb-6 max-w-4xl mx-auto">
        <ol className="flex items-center justify-between">
          {STEPS.map((step, idx) => {
            const isDone = currentStep > step.id;
            const isCurrent = currentStep === step.id;

            return (
              <li key={step.id} className="relative flex-1 flex flex-col items-center">
                {idx > 0 && (
                  <div
                    className={`absolute top-3.5 right-1/2 left-[-50%] h-[1px] -z-0 transition-colors ${
                      isDone ? 'bg-cardinal' : 'bg-hairline'
                    }`}
                  />
                )}
                <div
                  className={`relative z-10 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-colors duration-200 ${
                    isDone
                      ? 'bg-cardinal text-porcelain'
                      : isCurrent
                      ? 'bg-porcelain border-2 border-cardinal text-cardinal'
                      : 'bg-snow border border-hairline text-graphite-subtle'
                  }`}
                >
                  {isDone ? <CheckCircle2 className="w-4 h-4" /> : step.id}
                </div>
                <span
                  className={`mt-1.5 text-[11px] font-medium hidden sm:block ${
                    isCurrent ? 'text-graphite font-semibold' : 'text-graphite-muted'
                  }`}
                >
                  {step.title}
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Stepper Card */}
      <div className="bg-porcelain border border-hairline rounded-[12px] p-6 sm:p-8 shadow-panel max-w-4xl mx-auto">
        <form onSubmit={handleSubmit(onSubmit)}>
          {/* STEP 1: Basic Demographics */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div className="pb-3 border-b border-hairline">
                <h3 className="text-base font-bold font-heading text-graphite">1. Patient Demographics</h3>
                <p className="text-xs text-graphite-muted">Primary identity, age, and consent declaration.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input
                  label="Patient legal full name"
                  placeholder="e.g. Johnathan Doe"
                  {...register('name')}
                  error={errors.name?.message}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    label="Age (years)"
                    type="number"
                    placeholder="45"
                    {...register('age')}
                    error={errors.age?.message}
                  />
                  <div>
                    <label className="text-xs font-medium text-graphite mb-1.5 block">Sex</label>
                    <select
                      {...register('sex')}
                      className="w-full px-3 py-2 text-sm bg-porcelain text-graphite rounded-[6px] border border-hairline"
                    >
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <Input label="Date of birth (optional)" type="date" {...register('dob')} />
                <div>
                  <label className="text-xs font-medium text-graphite mb-1.5 block">Blood group</label>
                  <select
                    {...register('blood_group')}
                    className="w-full px-3 py-2 text-sm bg-porcelain text-graphite rounded-[6px] border border-hairline"
                  >
                    <option value="">Select...</option>
                    <option value="A+">A+</option>
                    <option value="A-">A-</option>
                    <option value="B+">B+</option>
                    <option value="B-">B-</option>
                    <option value="AB+">AB+</option>
                    <option value="AB-">AB-</option>
                    <option value="O+">O+</option>
                    <option value="O-">O-</option>
                  </select>
                </div>
                <Input label="Height (cm)" type="number" step="0.1" placeholder="175" {...register('height_cm')} />
                <Input label="Weight (kg)" type="number" step="0.1" placeholder="70" {...register('weight_kg')} />
              </div>

              <Input label="Contact phone number (optional)" placeholder="+1 (555) 000-0000" {...register('phone')} />

              <div className="pt-2">
                <label className="flex items-start gap-2.5 text-xs text-graphite-muted cursor-pointer">
                  <input type="checkbox" {...register('consent_confirmed')} className="mt-0.5 rounded text-cardinal" />
                  <span>
                    I confirm patient consent has been obtained for clinical examination and local decision-support analysis.
                  </span>
                </label>
                {errors.consent_confirmed && (
                  <p className="text-xs text-cardinal mt-1 font-medium">{errors.consent_confirmed.message}</p>
                )}
              </div>
            </div>
          )}

          {/* STEP 2: Vital Signs */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="pb-3 border-b border-hairline">
                <h3 className="text-base font-bold font-heading text-graphite">2. Vital Signs</h3>
                <p className="text-xs text-graphite-muted">Enter recorded bedside parameters (press Next to skip unmeasured fields).</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Input
                  label="Temperature (°C or °F)"
                  type="number"
                  step="0.1"
                  placeholder="37.0"
                  {...register('temp_c')}
                  helperText="Values >45 are converted to Celsius automatically."
                />
                <Input label="Heart rate (bpm)" type="number" placeholder="72" {...register('hr')} />
                <div className="grid grid-cols-2 gap-2">
                  <Input label="Systolic BP" type="number" placeholder="120" {...register('bp_sys')} />
                  <Input label="Diastolic BP" type="number" placeholder="80" {...register('bp_dia')} />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="SpO2 oxygen saturation (%)" type="number" placeholder="98" {...register('spo2')} />
                <Input label="Respiratory rate (/min)" type="number" placeholder="16" {...register('rr')} />
              </div>
            </div>
          )}

          {/* STEP 3: Clinical History */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="pb-3 border-b border-hairline">
                <h3 className="text-base font-bold font-heading text-graphite">3. Clinical History</h3>
                <p className="text-xs text-graphite-muted">Structured physician anamnesis and modality-specific queries.</p>
              </div>

              <Input
                label="Chief complaint / Reason for imaging"
                placeholder="e.g. Cough and progressive dyspnea for 2 weeks"
                {...register('chief_complaint')}
              />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Onset & duration" placeholder="e.g. Gradual, 3 weeks" {...register('onset_duration')} />
                <Input label="Associated symptoms" placeholder="e.g. Low grade fever, right pleuritic pain" {...register('associated_symptoms')} />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Past medical / surgical history" placeholder="e.g. Hypertension, appendectomy" {...register('past_history')} />
                <Input label="Known allergies" placeholder="e.g. Penicillin, NSAIDs" {...register('allergies')} />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Input label="Family history" placeholder="e.g. Father had COPD" {...register('family_history')} />
                <Input label="Lifestyle / Occupational exposure" placeholder="e.g. Former smoker (10 pack-yrs)" {...register('lifestyle')} />
              </div>

              {/* Modality Selector to display specific questions */}
              <div className="pt-2 border-t border-hairline">
                <label className="text-xs font-semibold text-graphite mb-2 block">
                  Select intended imaging scan to view focused questions:
                </label>
                <div className="flex gap-2 mb-3">
                  {['NONE', 'SKIN', 'XRAY', 'MRI'].map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setSelectedScanType(type)}
                      className={`px-3 py-1.5 rounded-[6px] text-xs font-medium border transition-colors ${
                        selectedScanType === type
                          ? 'bg-blush border-cardinal text-cardinal font-semibold'
                          : 'bg-snow border-hairline text-graphite-muted'
                      }`}
                    >
                      {type === 'NONE' ? 'General' : type}
                    </button>
                  ))}
                </div>

                {selectedScanType === 'SKIN' && (
                  <div className="p-3 bg-snow rounded-[8px] border border-hairline space-y-3 text-xs">
                    <Input label="Skin lesion location on body" placeholder="e.g. Posterior right calf" {...register('skin_site')} />
                    <Input label="Change in size, colour, or itching/bleeding" placeholder="e.g. Darkened over 6 weeks" {...register('skin_change')} />
                    <Input label="Sun exposure & skin cancer history" placeholder="e.g. Frequent sunburns in youth" {...register('skin_sun')} />
                  </div>
                )}

                {selectedScanType === 'XRAY' && (
                  <div className="p-3 bg-snow rounded-[8px] border border-hairline space-y-3 text-xs">
                    <Input label="Cough, fever, sputum characteristics" placeholder="e.g. Productive green sputum" {...register('chest_cough')} />
                    <Input label="TB contact or recent endemic travel" placeholder="e.g. No known contacts" {...register('chest_tb')} />
                  </div>
                )}

                {selectedScanType === 'MRI' && (
                  <div className="p-3 bg-snow rounded-[8px] border border-hairline space-y-3 text-xs">
                    <Input label="Headache, focal sensory/motor deficits, seizures" placeholder="e.g. Left sided weakness" {...register('brain_headache')} />
                  </div>
                )}
              </div>

              <Input
                label="Doctor's specific clinical question for AI synthesis"
                placeholder="e.g. Evaluate for pneumonic consolidation vs pleural effusion"
                {...register('doctor_question')}
              />
            </div>
          )}

          {/* STEP 4: Medicines Table */}
          {currentStep === 4 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-hairline">
                <div>
                  <h3 className="text-base font-bold font-heading text-graphite">4. Current Medications</h3>
                  <p className="text-xs text-graphite-muted">Active drug therapy and indications.</p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={handleAddMedicineRow}>
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  Add row
                </Button>
              </div>

              <div className="space-y-3">
                {medicines.map((med, idx) => (
                  <div key={idx} className="p-3 bg-snow rounded-[8px] border border-hairline grid grid-cols-1 sm:grid-cols-6 gap-2 items-center text-xs">
                    <input
                      type="text"
                      placeholder="Drug name (e.g. Amoxicillin)"
                      value={med.drug_name}
                      onChange={(e) => handleMedicineChange(idx, 'drug_name', e.target.value)}
                      className="px-2 py-1.5 bg-porcelain rounded border border-hairline text-xs col-span-2"
                    />
                    <input
                      type="text"
                      placeholder="Dose (e.g. 500mg)"
                      value={med.dose}
                      onChange={(e) => handleMedicineChange(idx, 'dose', e.target.value)}
                      className="px-2 py-1.5 bg-porcelain rounded border border-hairline text-xs"
                    />
                    <input
                      type="text"
                      placeholder="Frequency (e.g. TDS)"
                      value={med.frequency}
                      onChange={(e) => handleMedicineChange(idx, 'frequency', e.target.value)}
                      className="px-2 py-1.5 bg-porcelain rounded border border-hairline text-xs"
                    />
                    <input
                      type="text"
                      placeholder="Indication (e.g. Infection)"
                      value={med.indication}
                      onChange={(e) => handleMedicineChange(idx, 'indication', e.target.value)}
                      className="px-2 py-1.5 bg-porcelain rounded border border-hairline text-xs"
                    />
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => handleRemoveMedicineRow(idx)}
                        disabled={medicines.length === 1}
                        className="text-graphite-muted hover:text-cardinal p-1 disabled:opacity-30"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* STEP 5: Review and Confirm */}
          {currentStep === 5 && (
            <div className="space-y-4 text-xs">
              <div className="pb-3 border-b border-hairline">
                <h3 className="text-base font-bold font-heading text-graphite">5. Review Clinical Intake</h3>
                <p className="text-xs text-graphite-muted">Verify patient parameters before creating diagnostic case.</p>
              </div>

              <div className="bg-snow p-4 rounded-[8px] border border-hairline space-y-3">
                <div className="grid grid-cols-2 gap-2 text-graphite">
                  <div><span className="text-graphite-muted block">Name:</span> {formValues.name}</div>
                  <div><span className="text-graphite-muted block">Age / Sex:</span> {formValues.age} yrs • {formValues.sex}</div>
                  <div><span className="text-graphite-muted block">Blood Group:</span> {formValues.blood_group || 'N/A'}</div>
                  <div><span className="text-graphite-muted block">Phone:</span> {formValues.phone || 'N/A'}</div>
                </div>

                <div className="pt-2 border-t border-hairline">
                  <span className="text-graphite-muted block">Vitals Summary:</span>
                  <span className="text-graphite">
                    Temp: {formValues.temp_c || '-'} °C • HR: {formValues.hr || '-'} bpm • BP: {formValues.bp_sys || '-'}/{formValues.bp_dia || '-'} • SpO2: {formValues.spo2 || '-'}%
                  </span>
                </div>

                <div className="pt-2 border-t border-hairline">
                  <span className="text-graphite-muted block">Chief Complaint:</span>
                  <span className="text-graphite font-medium">{formValues.chief_complaint || 'None provided'}</span>
                </div>
              </div>
            </div>
          )}

          {/* Step Actions */}
          <div className="flex items-center justify-between mt-8 pt-4 border-t border-hairline">
            {currentStep > 1 ? (
              <Button type="button" variant="outline" size="sm" onClick={() => setCurrentStep((p) => p - 1)}>
                <ChevronLeft className="w-4 h-4 mr-1" />
                Previous step
              </Button>
            ) : (
              <Link to="/doctor/patients">
                <Button type="button" variant="ghost" size="sm">Cancel</Button>
              </Link>
            )}

            {currentStep < 5 ? (
              <Button type="button" variant="primary" size="sm" onClick={handleNextStep}>
                Next step
                <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button type="submit" variant="primary" size="md" isLoading={isLoading}>
                Save patient & open workspace
              </Button>
            )}
          </div>
        </form>
      </div>
    </DoctorLayout>
  );
};
