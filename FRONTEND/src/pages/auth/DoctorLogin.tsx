import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { LoginIntroOverlay } from '../../components/ui/LoginIntroOverlay';
import { useAuth } from '../../context/AuthContext';
import { apiClient, ApiError } from '../../api/client';
import { Clock, AlertCircle, ArrowRight, KeyRound, Sparkles } from 'lucide-react';

const loginSchema = z.object({
  reg_number: z.string().min(3, 'Registration number is required'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export const DoctorLogin: React.FC = () => {
  const navigate = useNavigate();
  const { loginDoctor } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [introDoctorName, setIntroDoctorName] = useState<string | null>(null);
  const [mustChangePwd, setMustChangePwd] = useState(false);
  const [userRegNumber, setUserRegNumber] = useState('');
  const [pendingInfo, setPendingInfo] = useState<{
    status: string;
    message: string;
    reg_number?: string;
    full_name?: string;
    status_reason?: string;
  } | null>(null);

  // Forgot password modal state
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotReg, setForgotReg] = useState('');
  const [forgotDob, setForgotDob] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    setPendingInfo(null);
    try {
      const res = await loginDoctor(data.reg_number, data.password);
      if (res.status === 'success') {
        toast.success(`Welcome back, ${res.user?.full_name || 'Doctor'}`);
        setMustChangePwd(Boolean(res.must_change_password));
        setUserRegNumber(data.reg_number);
        // Play premium intro greeting and 2-cycle animated logo
        setIntroDoctorName(res.user?.full_name || 'Doctor');
      } else if (res.status === 'pending_review' || res.status === 'needs_info' || res.status === 'rejected') {
        setPendingInfo(res);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('Could not authenticate. Verify credentials and try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!forgotReg || !forgotDob) {
      toast.error('Both Registration Number and Date of Birth are required');
      return;
    }
    setForgotLoading(true);
    try {
      const res = await apiClient<{ message: string }>('/api/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ reg_number: forgotReg, dob: forgotDob }),
      });
      toast.success(res.message);
      setShowForgotModal(false);
    } catch (err: any) {
      toast.error(err.message || 'Could not submit password reset request');
    } finally {
      setForgotLoading(false);
    }
  };

  const fillDemoDoctor = (reg: string, pass: string) => {
    setValue('reg_number', reg);
    setValue('password', pass);
  };

  return (
    <AuthLayout
      title="Doctor sign in"
      subtitle="Access patient diagnostics, multimodality scans, and AI clinical summaries."
    >
      {pendingInfo ? (
        <div className="flex flex-col gap-4 py-2">
          <div className="flex items-center justify-between pb-3 border-b border-hairline">
            <span className="text-sm font-medium text-graphite">Application Status</span>
            <StatusChip status={pendingInfo.status} />
          </div>

          <div className="bg-snow rounded-[8px] p-4 border border-hairline">
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-cardinal shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-graphite">
                  {pendingInfo.full_name || 'Doctor applicant'}
                </h4>
                <p className="text-xs text-graphite-muted mt-1 leading-relaxed">
                  {pendingInfo.status_reason || pendingInfo.message}
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-2 pt-2">
            <Link to={`/application-status?reg=${pendingInfo.reg_number}`}>
              <Button variant="primary" size="md" className="w-full">
                View live review timeline
              </Button>
            </Link>
            <Button
              variant="secondary"
              size="md"
              className="w-full"
              onClick={() => setPendingInfo(null)}
            >
              Back to login
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            label="Medical council registration number"
            placeholder="e.g. MC-2015-88412"
            autoComplete="username"
            {...register('reg_number')}
            error={errors.reg_number?.message}
          />

          <div>
            <Input
              label="Password"
              type="password"
              placeholder="••••••••••••"
              autoComplete="current-password"
              {...register('password')}
              error={errors.password?.message}
            />
            <div className="flex justify-end mt-1.5">
              <button
                type="button"
                onClick={() => setShowForgotModal(true)}
                className="text-xs text-graphite-muted hover:text-cardinal transition-colors"
              >
                Forgot password?
              </button>
            </div>
          </div>

          <Button type="submit" variant="primary" size="lg" className="w-full mt-2" isLoading={isLoading}>
            Sign in to clinical portal
          </Button>

          {/* Quick Demo Credentials for Reviewers */}
          <div className="pt-4 border-t border-hairline mt-4">
            <div className="flex items-center gap-1.5 text-xs text-graphite-muted mb-2 font-medium">
              <Sparkles className="w-3.5 h-3.5 text-cardinal" />
              <span>Demo credentials (click to pre-fill):</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => fillDemoDoctor('MC-2015-88412', 'DoctorSecure#1')}
                className="p-2 rounded-[6px] border border-hairline bg-snow hover:bg-blush hover:border-cardinal/30 text-left transition-colors"
              >
                <div className="font-semibold text-graphite">Dr. Aris Thorne</div>
                <div className="text-[11px] text-[#1F7A5C] font-medium">Approved doctor</div>
              </button>
              <button
                type="button"
                onClick={() => fillDemoDoctor('MC-2021-49102', 'DoctorSecure#2')}
                className="p-2 rounded-[6px] border border-hairline bg-snow hover:bg-blush hover:border-cardinal/30 text-left transition-colors"
              >
                <div className="font-semibold text-graphite">Dr. Elena Rostova</div>
                <div className="text-[11px] text-blue-600 font-medium">Pending review</div>
              </button>
            </div>
          </div>

          <div className="pt-3 text-center text-xs text-graphite-muted">
            New doctor practicing in this facility?{' '}
            <Link to="/register" className="font-medium text-cardinal hover:underline">
              Submit registration
            </Link>
          </div>
        </form>
      )}

      {/* Forgot Password Modal */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-blush flex items-center justify-center text-cardinal shrink-0">
                <KeyRound className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-graphite">Request password reset</h3>
                <p className="text-xs text-graphite-muted mt-1 leading-relaxed">
                  Provide your registered council number and date of birth. The administrator will verify and issue a temporary one-time password.
                </p>
              </div>
            </div>

            <form onSubmit={handleForgotPassword} className="space-y-3">
              <Input
                label="Registration number"
                placeholder="e.g. MC-2015-88412"
                value={forgotReg}
                onChange={(e) => setForgotReg(e.target.value)}
                required
              />
              <Input
                label="Date of birth"
                type="date"
                value={forgotDob}
                onChange={(e) => setForgotDob(e.target.value)}
                required
              />

              <div className="flex items-center justify-end gap-2 pt-4 border-t border-hairline">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowForgotModal(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm" isLoading={forgotLoading}>
                  Submit reset request
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Cinematic Login Intro Overlay */}
      {introDoctorName && (
        <LoginIntroOverlay
          name={introDoctorName}
          role="doctor"
          onComplete={() => {
            if (mustChangePwd) {
              navigate('/change-temp-password', { state: { reg_number: userRegNumber } });
            } else {
              navigate('/doctor/dashboard');
            }
          }}
        />
      )}
    </AuthLayout>
  );
};
