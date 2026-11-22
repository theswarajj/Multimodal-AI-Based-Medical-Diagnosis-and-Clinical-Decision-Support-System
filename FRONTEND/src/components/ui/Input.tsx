import React, { InputHTMLAttributes, forwardRef } from 'react';
import clsx from 'clsx';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className = '', id, ...props }, ref) => {
    const inputId = id || props.name || Math.random().toString(36).substring(2, 9);

    return (
      <div className="w-full flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-xs font-medium text-graphite flex items-center justify-between"
          >
            <span>{label}</span>
          </label>
        )}
        <input
          id={inputId}
          ref={ref}
          className={clsx(
            'w-full px-3 py-2 text-sm bg-porcelain text-graphite rounded-[6px] border transition-colors duration-150',
            'placeholder:text-graphite-light',
            'focus:outline-none focus:border-cardinal focus:ring-1 focus:ring-cardinal',
            error
              ? 'border-cardinal focus:border-cardinal'
              : 'border-hairline hover:border-graphite-light',
            'disabled:bg-snow disabled:text-graphite-subtle disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        {error ? (
          <p className="text-xs text-cardinal font-medium mt-0.5">{error}</p>
        ) : helperText ? (
          <p className="text-xs text-graphite-muted mt-0.5">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = 'Input';
