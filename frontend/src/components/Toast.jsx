import { useState, useCallback } from 'react';

let toastId = 0;

/**
 * Toast notification system.
 * Returns [toasts, addToast] — render <ToastContainer toasts={toasts} />
 */
export function useToasts() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'update') => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return [toasts, addToast];
}

export function ToastContainer({ toasts }) {
  const getTypeClasses = (type) => {
    switch (type) {
      case 'rank-change':
        return 'bg-gradient-to-br from-[rgba(16,185,129,0.15)] to-[rgba(99,102,241,0.1)] border-[rgba(16,185,129,0.3)] text-green';
      case 'displaced':
        return 'bg-gradient-to-br from-[rgba(239,68,68,0.15)] to-[rgba(239,68,68,0.05)] border-[rgba(239,68,68,0.3)] text-red';
      case 'update':
      default:
        return 'bg-gradient-to-br from-[rgba(99,102,241,0.15)] to-[rgba(99,102,241,0.05)] border-[rgba(99,102,241,0.3)] text-accent-hover';
    }
  };

  return (
    <div className="fixed top-5 right-5 z-[1000] flex flex-col gap-2.5">
      {toasts.map((t) => (
        <div key={t.id} className={`px-5 py-3.5 rounded-lg text-sm font-medium min-w-[320px] max-w-[420px] animate-[toastIn_0.4s_ease,toastOut_0.4s_ease_3.6s_forwards] shadow-[0_8px_32px_rgba(0,0,0,0.4)] border ${getTypeClasses(t.type)}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
