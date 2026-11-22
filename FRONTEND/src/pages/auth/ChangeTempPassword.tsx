import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { PasswordStrength } from '../../components/ui/PasswordStrength';
import { apiClient, ApiError } from '../../api/client';
import { KeyRound, ShieldAlert } from 'lucide-react';

const changePwdSchema = z
  .object({
    reg_number: z.string().min(1, 'Registration number is required'),
    temp_password: z.string().min(1, 'Temporary password is required'),
    new_password: z.string().min(8, 'New password must be at least 8 characters'),
    confirm_new_password: z.string().min(1, 'Confirm your new password'),
  })
  .refine((data) => data.new_password === data.confirm_new_password, {
    message: 'Passwords do not match',
    path: ['confirm_new_password'],
  });

type ChangePwdFormData = z.infer<typeof changePwdSchema>;

export const ChangeTempPassword: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const initialReg = (location.state as any)?.reg_number || '';
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ChangePwdFormData>({
    resolver: zodResolver(changePwdSchema),
    defaultValues: {
      reg_number: initialReg,
    },
  });

  const newPasswordValue = watch('new_password') || '';

  const onSubmit = async (data: ChangePwdFormData) => {
    setIsLoading(true);
    try {
      const res = await apiClient<{ status: string; message: string }>(
        '/api/auth/change-temp-password',
        {
          method: 'POST',
          body: JSON.stringify({
            reg_number: data.reg_number,
            temp_password: data.temp_password,
            new_password: data.new_password,
          }),
        }
      );
      toast.success(res.message);
      navigate('/login');
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.message);
      } else {
        toast.error('Could not update password. Verify temporary credentials.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Set permanent password"
      subtitle="You logged in with a temporary administrative password. Please establish a new personal password."
    >
      <div className="mb-4 p-3 bg-amber-50 rounded-[6px] border border-amber-200/80 flex items-start gap-3 text-xs text-graphite">
        <ShieldAlert className="w-4 h-4 text-[#B7791F] shrink-0 mt-0.5" />
        <p className="leading-relaxed">
          For clinical safety and audit integrity, temporary passwords must be changed immediately upon sign-in.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Medical council registration number"
          {...register('reg_number')}
          error={errors.reg_number?.message}
        />

        <Input
          label="Temporary password"
          type="password"
          placeholder="Enter the one-time password"
          {...register('temp_password')}
          error={errors.temp_password?.message}
        />

        <div>
          <Input
            label="New password"
            type="password"
            placeholder="At least 8 characters"
            {...register('new_password')}
            error={errors.new_password?.message}
          />
          <PasswordStrength password={newPasswordValue} />
        </div>

        <Input
          label="Confirm new password"
          type="password"
          placeholder="Re-enter new password"
          {...register('confirm_new_password')}
          error={errors.confirm_new_password?.message}
        />

        <Button type="submit" variant="primary" size="lg" className="w-full mt-2" isLoading={isLoading}>
          Save new password and proceed
        </Button>

        <div className="pt-3 text-center text-xs">
          <Link to="/login" className="text-graphite-muted hover:text-cardinal transition-colors font-medium">
            Cancel and return to sign in
          </Link>
        </div>
      </form>
    </AuthLayout>
  );
};
