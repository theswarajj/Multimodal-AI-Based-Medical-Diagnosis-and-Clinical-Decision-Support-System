import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { User, AuthResponse } from '../types/auth';
import { apiClient } from '../api/client';
import { IdleTimerModal } from '../components/ui/IdleTimerModal';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  loginDoctor: (regNumber: string, password: string) => Promise<AuthResponse>;
  loginAdmin: (email: string, password: string, totpCode: string) => Promise<AuthResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const IDLE_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes
const WARNING_BEFORE_MS = 2 * 60 * 1000; // Warning 2 mins before logout

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showIdleModal, setShowIdleModal] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(120);

  const lastActivityRef = useRef<number>(Date.now());
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const refreshUser = useCallback(async () => {
    try {
      const data = await apiClient<User>('/api/auth/me');
      setUser(data);
    } catch {
      setUser(null);
      localStorage.removeItem('clinical_lens_jwt');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  // Idle timeout tracking
  const resetActivity = useCallback(() => {
    lastActivityRef.current = Date.now();
    if (showIdleModal) {
      setShowIdleModal(false);
    }
  }, [showIdleModal]);

  useEffect(() => {
    if (!user) return;

    const events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    events.forEach((evt) => window.addEventListener(evt, resetActivity));

    const checkInterval = setInterval(() => {
      const now = Date.now();
      const elapsed = now - lastActivityRef.current;

      if (elapsed >= IDLE_TIMEOUT_MS) {
        logout();
      } else if (elapsed >= IDLE_TIMEOUT_MS - WARNING_BEFORE_MS) {
        setShowIdleModal(true);
        setRemainingSeconds(Math.ceil((IDLE_TIMEOUT_MS - elapsed) / 1000));
      } else {
        setShowIdleModal(false);
      }
    }, 1000);

    return () => {
      events.forEach((evt) => window.removeEventListener(evt, resetActivity));
      clearInterval(checkInterval);
    };
  }, [user, resetActivity]);

  const loginDoctor = async (regNumber: string, password: string): Promise<AuthResponse> => {
    const res = await apiClient<AuthResponse>('/api/auth/doctor/login', {
      method: 'POST',
      body: JSON.stringify({ reg_number: regNumber, password }),
    });

    if (res.status === 'success' && res.access_token && res.user) {
      localStorage.setItem('clinical_lens_jwt', res.access_token);
      setUser(res.user);
      lastActivityRef.current = Date.now();
    }
    return res;
  };

  const loginAdmin = async (email: string, password: string, totpCode: string): Promise<AuthResponse> => {
    const res = await apiClient<AuthResponse>('/api/auth/admin/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, totp_code: totpCode }),
    });

    if (res.status === 'success' && res.access_token && res.user) {
      localStorage.setItem('clinical_lens_jwt', res.access_token);
      setUser(res.user);
      lastActivityRef.current = Date.now();
    }
    return res;
  };

  const logout = async () => {
    try {
      await apiClient('/api/auth/logout', { method: 'POST' });
    } catch {
      // Continue client cleanup even if network fails
    } finally {
      localStorage.removeItem('clinical_lens_jwt');
      setUser(null);
      setShowIdleModal(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        loginDoctor,
        loginAdmin,
        logout,
        refreshUser,
      }}
    >
      {children}
      <IdleTimerModal
        isOpen={showIdleModal}
        remainingSeconds={remainingSeconds}
        onExtend={resetActivity}
        onLogout={logout}
      />
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
