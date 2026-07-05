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
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
