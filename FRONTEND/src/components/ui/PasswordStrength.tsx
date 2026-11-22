import React from 'react';

interface PasswordStrengthProps {
  password: string;
}

export const PasswordStrength: React.FC<PasswordStrengthProps> = ({ password }) => {
  if (!password) return null;

  const getScore = (pwd: string) => {
    let score = 0;
    if (pwd.length >= 8) score += 1;
    if (pwd.length >= 12) score += 1;
    if (/[A-Z]/.test(pwd)) score += 1;
    if (/[0-9]/.test(pwd)) score += 1;
    if (/[^A-Za-z0-9]/.test(pwd)) score += 1;
    return score; // 0 to 5
  };

  const score = getScore(password);

  const getLabel = () => {
    if (score <= 1) return { text: 'Weak', color: 'text-amber-700', width: '20%', barColor: 'bg-amber-500' };
    if (score <= 3) return { text: 'Fair', color: 'text-amber-800', width: '50%', barColor: 'bg-amber-500' };
    if (score === 4) return { text: 'Strong', color: 'text-[#1F7A5C]', width: '80%', barColor: 'bg-[#1F7A5C]' };
    return { text: 'Very strong', color: 'text-[#1F7A5C]', width: '100%', barColor: 'bg-[#1F7A5C]' };
  };

  const current = getLabel();

  return (
    <div className="w-full mt-1.5">
      <div className="flex items-center justify-between text-xs text-graphite-muted mb-1">
        <span>Password strength</span>
        <span className={`font-medium ${current.color}`}>{current.text}</span>
      </div>
      <div className="w-full h-1 bg-hairline rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-300 rounded-full ${current.barColor}`}
          style={{ width: current.width }}
        />
      </div>
    </div>
  );
};
