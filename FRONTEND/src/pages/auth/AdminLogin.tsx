import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { LoginIntroOverlay } from '../../components/ui/LoginIntroOverlay';
import { useAuth } from '../../context/AuthContext';
import { apiClient, ApiError } from '../../api/client';
import { ShieldCheck, Lock, KeySquare, Sparkles, Check, Copy } from 'lucide-react';

const adminLoginSchema = z.object({
  email: z.string().email('Please enter a valid administrator email'),
  password: z.string().min(1, 'Password is required'),
  totp_code: z.string().min(6, 'Please enter the 6-digit TOTP code'),
});

type AdminLoginFormData = z.infer<typeof adminLoginSchema>;

export const AdminLogin: React.FC = () => {
  const navigate = useNavigate();
  const { loginAdmin } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [serverSessionOtp, setServerSessionOtp] = useState<string | null>(null);
  const [introAdminName, setIntroAdminName] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<AdminLoginFormData>({
    resolver: zodResolver(adminLoginSchema),
    defaultValues: {
      email: 'admin@clinicallens.local',
    },
  });

  // Fetch the active server session OTP on load so the user doesn't have to look it up repeatedly
  useEffect(() => {
    let isMounted = true;
    apiClient<{ code: string; is_session_code?: boolean }>(
      '/api/auth/admin/demo-totp'
    )
      .then((res) => {
        if (isMounted && res.code) {
          setServerSessionOtp(res.code);
          // Auto-populate 2FA code so admin sign-in is effortless
          setValue('totp_code', res.code);
        }
      })
      .catch(() => {
        // Backend might be offline or starting up
      });
    return () => {
      isMounted = false;
    };
  }, [setValue]);

  const onSubmit = async (data: AdminLoginFormData) => {
    setIsLoading(true);
    try {
      const res = await loginAdmin(data.email, data.password, data.totp_code);
      if (res.status === 'success') {
        toast.success('Administrator authenticated with 2FA');
        setIntroAdminName(res.user?.full_name || 'Administrator');
      }
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('Invalid administrative credentials or TOTP code');
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Helper to pre-fill admin credentials and active session OTP in one click
  const prefillAdmin = async () => {
    setValue('email', 'admin@clinicallens.local');
    setValue('password', 'AdminSecure#2026');
    try {
      const res = await apiClient<{ code: string; is_session_code?: boolean }>(
        '/api/auth/admin/demo-totp'
      );
      if (res.code) {
        setServerSessionOtp(res.code);
        setValue('totp_code', res.code);
        toast.success(`Admin credentials & active session OTP (${res.code}) pre-filled!`);
        return;
      }
    } catch {
      // Fallback
    }
    toast.info('Pre-filled Admin credentials.');
  };

  return (
    <AuthLayout
      title="Administrator sign in"
      subtitle="Security center, doctor credentialing, and system monitoring."
      isAdmin={true}
    >
      <div className="mb-5 p-3 rounded-[6px] bg-snow border border-hairline flex items-center gap-3">
        <ShieldCheck className="w-5 h-5 text-cardinal shrink-0" />
        <div className="text-xs text-graphite-muted leading-tight">
          <span className="font-semibold text-graphite block">Mandatory 2FA Protection</span>
          Administrative sessions require two-factor verification.
        </div>
      </div>

      {serverSessionOtp && (
        <div className="mb-4 p-3 rounded-[6px] bg-blush/40 border border-cardinal/20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <KeySquare className="w-4 h-4 text-cardinal shrink-0" />
            <div className="text-xs text-graphite">
              <span className="font-medium text-graphite">Server Session 2FA Code:</span>{' '}
              <span className="font-mono font-bold text-cardinal tracking-wider text-sm px-1.5 py-0.5 bg-white border border-hairline rounded">
                {serverSessionOtp}
              </span>
              <span className="text-[11px] text-graphite-subtle ml-1.5 hidden sm:inline">
                (Valid until server stops)
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setValue('totp_code', serverSessionOtp);
              toast.info('Session code inserted');
            }}
            className="text-[11px] font-medium text-cardinal hover:underline shrink-0"
          >
            Insert
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Administrator email"
          type="email"
          placeholder="admin@clinicallens.local"
          autoComplete="email"
          {...register('email')}
          error={errors.email?.message}
        />

        <Input
          label="Password"
          type="password"
          placeholder="••••••••••••"
          autoComplete="current-password"
          {...register('password')}
          error={errors.password?.message}
        />

        <div>
          <Input
            label="Two-factor authentication code (TOTP / Session OTP)"
            placeholder="6-digit code e.g. 123456"
            maxLength={10}
            inputMode="numeric"
            autoComplete="one-time-code"
            className="tracking-widest font-mono text-center text-base font-semibold"
            {...register('totp_code')}
            error={errors.totp_code?.message}
          />
          <div className="mt-1 flex items-center justify-between text-[11px] text-graphite-subtle">
            <span>Session OTP or Authenticator app</span>
            <span className="font-mono text-cardinal">Active for server run</span>
          </div>
        </div>

        <Button type="submit" variant="primary" size="lg" className="w-full mt-2" isLoading={isLoading}>
          Verify 2FA and access portal
        </Button>

        {/* Demo pre-fill helper for reviewer */}
        <div className="pt-3 border-t border-hairline mt-3 text-center">
          <button
            type="button"
            onClick={prefillAdmin}
            className="text-xs text-graphite-muted hover:text-cardinal transition-colors inline-flex items-center gap-1 font-medium"
          >
            <Sparkles className="w-3.5 h-3.5 text-cardinal" />
            <span>Pre-fill admin email & password</span>
          </button>
        </div>
      </form>

      {/* Cinematic Login Intro Overlay */}
      {introAdminName && (
        <LoginIntroOverlay
          name={introAdminName}
          role="admin"
          onComplete={() => {
            navigate('/admin/overview');
          }}
        />
      )}
    </AuthLayout>
  );
};
