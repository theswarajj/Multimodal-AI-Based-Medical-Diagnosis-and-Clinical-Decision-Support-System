import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { useDropzone } from 'react-dropzone';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { PasswordStrength } from '../../components/ui/PasswordStrength';
import { apiClient, ApiError } from '../../api/client';
import {
  User,
  Award,
  FileCheck2,
  CheckCircle2,
  UploadCloud,
  FileText,
  X,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';

const registerSchema = z.object({
  full_name: z.string().min(3, 'Full name must be at least 3 characters'),
  dob: z.string().min(1, 'Date of birth is required'),
  email: z.string().email('Please enter a valid medical email address'),
  phone: z.string().min(7, 'Please provide a valid contact number'),
  reg_number: z.string().min(4, 'Registration number is required'),
  issuing_council: z.string().min(3, 'Issuing medical council is required'),
  reg_year: z.coerce.number().min(1950, 'Invalid year').max(new Date().getFullYear(), 'Year cannot be in the future'),
  qualification: z.string().min(2, 'Qualification is required (e.g. MBBS, MD)'),
  specialty: z.string().min(2, 'Specialty is required'),
  hospital_clinic: z.string().min(2, 'Hospital or clinic affiliation is required'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirm_password: z.string().min(1, 'Please confirm your password'),
  consent: z.literal(true, {
    errorMap: () => ({ message: 'You must confirm consent for terms and local patient data processing' }),
  }),
}).refine((data) => data.password === data.confirm_password, {
  message: 'Passwords do not match',
  path: ['confirm_password'],
});

type RegisterFormData = z.infer<typeof registerSchema>;

const STEPS = [
  { id: 1, title: 'Personal identity', icon: User },
  { id: 2, title: 'Medical credentials', icon: Award },
  { id: 3, title: 'Documents & security', icon: FileCheck2 },
  { id: 4, title: 'Review & submit', icon: CheckCircle2 },
];

export const DoctorRegister: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [submittedRegNumber, setSubmittedRegNumber] = useState('');

  // File uploads
  const [idProofFile, setIdProofFile] = useState<File | null>(null);
  const [certFile, setCertFile] = useState<File | null>(null);

  const {
    register,
    handleSubmit,
    trigger,
    watch,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    mode: 'onChange',
  });

  const passwordValue = watch('password') || '';
  const formValues = watch();

  // Step 1 validation check
  const handleNextStep = async () => {
    let valid = false;
    if (currentStep === 1) {
      valid = await trigger(['full_name', 'dob', 'email', 'phone']);
    } else if (currentStep === 2) {
      valid = await trigger([
        'reg_number',
        'issuing_council',
        'reg_year',
        'qualification',
        'specialty',
        'hospital_clinic',
      ]);
    } else if (currentStep === 3) {
      valid = await trigger(['password', 'confirm_password', 'consent']);
      if (!idProofFile || !certFile) {
        toast.error('Please upload both ID proof and registration certificate');
        return;
      }
    }
    if (valid) {
      setCurrentStep((prev) => Math.min(prev + 1, 4));
    }
  };

  const onSubmit = async (data: RegisterFormData) => {
    if (!idProofFile || !certFile) {
      toast.error('Both ID proof and registration certificate are required');
      return;
    }

    setIsLoading(true);
    try {
      const formData = new FormData();
      formData.append('full_name', data.full_name);
      formData.append('dob', data.dob);
      formData.append('email', data.email);
      formData.append('phone', data.phone);
      formData.append('reg_number', data.reg_number);
      formData.append('issuing_council', data.issuing_council);
      formData.append('reg_year', String(data.reg_year));
      formData.append('qualification', data.qualification);
      formData.append('specialty', data.specialty);
      formData.append('hospital_clinic', data.hospital_clinic);
      formData.append('password', data.password);
      formData.append('consent', 'true');
      formData.append('id_proof', idProofFile);
      formData.append('reg_cert', certFile);

      const res = await apiClient<{ status: string; message: string; reg_number: string }>(
        '/api/auth/doctor/register',
        {
          method: 'POST',
          body: formData,
        }
      );

      setSubmittedRegNumber(res.reg_number);
      setIsSuccess(true);
      toast.success('Registration submitted for administrative review');
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('Registration failed. Check network or server connection.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Dropzone for ID Proof
  const idDropzone = useDropzone({
    accept: { 'application/pdf': ['.pdf'], 'image/*': ['.jpg', '.jpeg', '.png'] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) setIdProofFile(acceptedFiles[0]);
    },
  });

  // Dropzone for Cert
  const certDropzone = useDropzone({
    accept: { 'application/pdf': ['.pdf'], 'image/*': ['.jpg', '.jpeg', '.png'] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) setCertFile(acceptedFiles[0]);
    },
  });

  if (isSuccess) {
    return (
      <AuthLayout
        title="Application under review"
        subtitle="Your medical credentials have been securely stored and queued for admin verification."
      >
        <div className="flex flex-col items-center text-center py-4">
          <div className="w-14 h-14 rounded-full bg-emerald-50 text-[#1F7A5C] flex items-center justify-center border border-emerald-200/80 mb-4">
            <CheckCircle2 className="w-8 h-8" />
          </div>

          <h3 className="text-base font-semibold text-graphite">
            Submission successful
          </h3>
          <p className="text-xs text-graphite-muted mt-2 max-w-[45ch] leading-relaxed">
            Your Medical Council Registration Number is:
          </p>
          <div className="mt-2 px-4 py-2 bg-snow rounded-[6px] border border-hairline font-mono text-sm font-semibold text-cardinal">
            {submittedRegNumber}
          </div>

          <p className="text-xs text-graphite-muted mt-4 max-w-[45ch] leading-relaxed">
            The administrator will cross-reference your council registration and uploaded certificate against official registries.
          </p>

          <div className="w-full mt-6 flex flex-col gap-2">
            <Link to={`/application-status?reg=${submittedRegNumber}`}>
              <Button variant="primary" size="md" className="w-full">
                Track review timeline
              </Button>
            </Link>
            <Link to="/login">
              <Button variant="ghost" size="md" className="w-full">
                Return to sign in
              </Button>
            </Link>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Doctor registration"
      subtitle="Register as an authorized clinician to order scans and run multimodal analyses."
    >
      {/* Real sequence Stepper */}
      <nav aria-label="Progress" className="mb-6">
        <ol className="flex items-center justify-between">
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
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

      <form onSubmit={handleSubmit(onSubmit)}>
        {/* STEP 1: Personal Details */}
        {currentStep === 1 && (
          <div className="space-y-4">
            <Input
              label="Full legal name"
              placeholder="e.g. Dr. Aris Thorne"
              {...register('full_name')}
              error={errors.full_name?.message}
            />
            <Input
              label="Date of birth"
              type="date"
              {...register('dob')}
              error={errors.dob?.message}
            />
            <Input
              label="Professional email address"
              type="email"
              placeholder="doctor@hospital.org"
              {...register('email')}
              error={errors.email?.message}
            />
            <Input
              label="Contact phone number"
              placeholder="+1 (555) 000-0000"
              {...register('phone')}
              error={errors.phone?.message}
            />
          </div>
        )}

        {/* STEP 2: Credentials */}
        {currentStep === 2 && (
          <div className="space-y-4">
            <Input
              label="Medical council registration number"
              placeholder="e.g. MC-2015-88412"
              {...register('reg_number')}
              error={errors.reg_number?.message}
            />
            <Input
              label="Issuing medical council / board"
              placeholder="e.g. Medical Council of California"
              {...register('issuing_council')}
              error={errors.issuing_council?.message}
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Registration year"
                type="number"
                placeholder="2015"
                {...register('reg_year')}
                error={errors.reg_year?.message}
              />
              <Input
                label="Primary qualification"
                placeholder="e.g. MBBS, MD"
                {...register('qualification')}
                error={errors.qualification?.message}
              />
            </div>
            <Input
              label="Clinical specialty"
              placeholder="e.g. Pulmonology / Dermatology"
              {...register('specialty')}
              error={errors.specialty?.message}
            />
            <Input
              label="Primary hospital or clinic"
              placeholder="e.g. St. Jude's Memorial Hospital"
              {...register('hospital_clinic')}
              error={errors.hospital_clinic?.message}
            />
          </div>
        )}

        {/* STEP 3: Documents & Security */}
        {currentStep === 3 && (
          <div className="space-y-4">
            {/* ID Proof Dropzone */}
            <div>
              <label className="text-xs font-medium text-graphite mb-1.5 block">
                Government / Institutional ID proof (PDF or Image)
              </label>
              {idProofFile ? (
                <div className="p-3 bg-snow rounded-[6px] border border-hairline flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-cardinal" />
                    <span className="font-medium text-graphite truncate max-w-[200px]">
                      {idProofFile.name}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIdProofFile(null)}
                    className="text-graphite-muted hover:text-cardinal"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div
                  {...idDropzone.getRootProps()}
                  className={`border border-dashed rounded-[6px] p-4 text-center cursor-pointer transition-colors ${
                    idDropzone.isDragActive
                      ? 'border-cardinal bg-blush'
                      : 'border-hairline bg-snow/50 hover:bg-snow'
                  }`}
                >
                  <input {...idDropzone.getInputProps()} />
                  <UploadCloud className="w-5 h-5 mx-auto text-graphite-muted mb-1" />
                  <p className="text-xs text-graphite-muted">
                    Click to select or drag & drop ID document (max 10MB)
                  </p>
                </div>
              )}
            </div>

            {/* Registration Certificate Dropzone */}
            <div>
              <label className="text-xs font-medium text-graphite mb-1.5 block">
                Medical registration certificate (PDF or Image)
              </label>
              {certFile ? (
                <div className="p-3 bg-snow rounded-[6px] border border-hairline flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-cardinal" />
                    <span className="font-medium text-graphite truncate max-w-[200px]">
                      {certFile.name}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setCertFile(null)}
                    className="text-graphite-muted hover:text-cardinal"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div
                  {...certDropzone.getRootProps()}
                  className={`border border-dashed rounded-[6px] p-4 text-center cursor-pointer transition-colors ${
                    certDropzone.isDragActive
                      ? 'border-cardinal bg-blush'
                      : 'border-hairline bg-snow/50 hover:bg-snow'
                  }`}
                >
                  <input {...certDropzone.getInputProps()} />
                  <UploadCloud className="w-5 h-5 mx-auto text-graphite-muted mb-1" />
                  <p className="text-xs text-graphite-muted">
                    Click to select or drag & drop medical certificate (max 10MB)
                  </p>
                </div>
              )}
            </div>

            <div>
              <Input
                label="Account password"
                type="password"
                placeholder="At least 8 characters"
                {...register('password')}
                error={errors.password?.message}
              />
              <PasswordStrength password={passwordValue} />
            </div>

            <Input
              label="Confirm password"
              type="password"
              placeholder="Re-enter password"
              {...register('confirm_password')}
              error={errors.confirm_password?.message}
            />

            <div className="pt-2">
              <label className="flex items-start gap-2.5 text-xs text-graphite-muted cursor-pointer">
                <input
                  type="checkbox"
                  {...register('consent')}
                  className="mt-0.5 rounded text-cardinal focus:ring-cardinal"
                />
                <span>
                  I confirm that all provided medical licensing details are accurate, and I agree to the local clinical data privacy policy.
                </span>
              </label>
              {errors.consent && (
                <p className="text-xs text-cardinal mt-1 font-medium">
                  {errors.consent.message}
                </p>
              )}
            </div>
          </div>
        )}

        {/* STEP 4: Review and Confirm */}
        {currentStep === 4 && (
          <div className="space-y-4 text-xs">
            <div className="bg-snow rounded-[8px] p-4 border border-hairline space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-hairline">
                <span className="font-semibold text-graphite">Personal details</span>
                <button
                  type="button"
                  onClick={() => setCurrentStep(1)}
                  className="text-cardinal hover:underline font-medium"
                >
                  Edit
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-graphite">
                <div>
                  <span className="text-graphite-muted block">Name:</span> {formValues.full_name}
                </div>
                <div>
                  <span className="text-graphite-muted block">DOB:</span> {formValues.dob}
                </div>
                <div>
                  <span className="text-graphite-muted block">Email:</span> {formValues.email}
                </div>
                <div>
                  <span className="text-graphite-muted block">Phone:</span> {formValues.phone}
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 pb-2 border-b border-hairline">
                <span className="font-semibold text-graphite">Medical credentials</span>
                <button
                  type="button"
                  onClick={() => setCurrentStep(2)}
                  className="text-cardinal hover:underline font-medium"
                >
                  Edit
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-graphite">
                <div>
                  <span className="text-graphite-muted block">Reg number:</span>{' '}
                  <span className="font-mono font-medium">{formValues.reg_number}</span>
                </div>
                <div>
                  <span className="text-graphite-muted block">Issuing council:</span>{' '}
                  {formValues.issuing_council}
                </div>
                <div>
                  <span className="text-graphite-muted block">Specialty:</span>{' '}
                  {formValues.specialty}
                </div>
                <div>
                  <span className="text-graphite-muted block">Hospital:</span>{' '}
                  {formValues.hospital_clinic}
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 pb-2 border-b border-hairline">
                <span className="font-semibold text-graphite">Attached proofs</span>
                <button
                  type="button"
                  onClick={() => setCurrentStep(3)}
                  className="text-cardinal hover:underline font-medium"
                >
                  Edit
                </button>
              </div>
              <div className="space-y-1 text-graphite">
                <div>ID Document: {idProofFile?.name || 'Attached'}</div>
                <div>Certificate: {certFile?.name || 'Attached'}</div>
              </div>
            </div>

            <p className="text-[11px] text-graphite-muted leading-relaxed">
              Upon clicking "Submit application", your registration will be reviewed by the administrator before access to patient imaging and inference is granted.
            </p>
          </div>
        )}

        {/* Stepper Navigation Actions */}
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-hairline">
          {currentStep > 1 ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCurrentStep((prev) => prev - 1)}
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Previous step
            </Button>
          ) : (
            <Link to="/login">
              <Button type="button" variant="ghost" size="sm">
                Cancel
              </Button>
            </Link>
          )}

          {currentStep < 4 ? (
            <Button type="button" variant="primary" size="sm" onClick={handleNextStep}>
              Next step
              <ChevronRight className="w-4 h-4 ml-1" />
            </Button>
          ) : (
            <Button type="submit" variant="primary" size="md" isLoading={isLoading}>
              Submit application
            </Button>
          )}
        </div>
      </form>
    </AuthLayout>
  );
};
