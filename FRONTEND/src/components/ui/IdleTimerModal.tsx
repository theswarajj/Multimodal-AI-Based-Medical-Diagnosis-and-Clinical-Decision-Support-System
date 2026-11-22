import React from 'react';
import { Button } from './Button';
import { ShieldAlert } from 'lucide-react';

interface IdleTimerModalProps {
  isOpen: boolean;
  remainingSeconds: number;
  onExtend: () => void;
  onLogout: () => void;
}

export const IdleTimerModal: React.FC<IdleTimerModalProps> = ({
  isOpen,
  remainingSeconds,
  onExtend,
  onLogout,
}) => {
  if (!isOpen) return null;

  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  const timeStr = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-graphite/40 backdrop-blur-sm p-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="idle-modal-title"
        className="w-full max-w-md bg-porcelain rounded-[12px] border border-hairline p-6 shadow-floating"
      >
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-full bg-blush flex items-center justify-center text-cardinal shrink-0">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <h3 id="idle-modal-title" className="text-base font-semibold text-graphite">
              Session idle warning
            </h3>
            <p className="text-sm text-graphite-muted mt-1.5 leading-relaxed">
              To protect local patient confidentiality, your session will automatically lock in{' '}
              <span className="font-semibold text-cardinal tabular-nums">{timeStr}</span> due to inactivity.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-hairline">
          <Button variant="ghost" size="sm" onClick={onLogout}>
            Log out now
          </Button>
          <Button variant="primary" size="sm" onClick={onExtend}>
            Extend session
          </Button>
        </div>
      </div>
    </div>
  );
};
