export type UserRole = 'admin' | 'doctor';

export type DoctorStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'NEEDS_INFO'
  | 'SUSPENDED'
  | 'LOCKED'
  | 'EXPIRED'
  | 'DEACTIVATED';

export interface DoctorProfileInfo {
  id: number;
  full_name: string;
  reg_number: string;
  specialty: string;
  hospital_clinic: string;
  status: DoctorStatus;
  allowed_models: string;
  daily_case_limit?: number;
  ai_summary_enabled?: boolean;
  pdf_export_enabled?: boolean;
}

export interface User {
  id: number;
  email: string;
  role: UserRole;
  full_name?: string;
  doctor?: DoctorProfileInfo;
}

export interface AuthResponse {
  status: 'success' | 'pending_review' | 'rejected' | 'needs_info';
  message: string;
  access_token?: string;
  token_type?: string;
  must_change_password?: boolean;
  user?: User;
  reg_number?: string;
  full_name?: string;
  doctor_status?: DoctorStatus;
  status_reason?: string;
  submitted_at?: string;
}

export interface ApplicationStatusResponse {
  reg_number: string;
  full_name: string;
  specialty: string;
  hospital_clinic: string;
  status: DoctorStatus;
  status_reason: string;
  submitted_at: string;
  updated_at: string;
}
