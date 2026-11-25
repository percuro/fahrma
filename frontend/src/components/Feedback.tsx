import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { FeedbackContext, type ConfirmOptions } from './feedback-context';
import { useT } from '../i18n';

interface PendingConfirm extends ConfirmOptions {
  message: string;
  resolve: (ok: boolean) => void;
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const timer = useRef<number | undefined>(undefined);

  const toast = useCallback((text: string) => {
    window.clearTimeout(timer.current);
    setMessage(text);
    timer.current = window.setTimeout(() => setMessage(''), 3500);
  }, []);

  const confirm = useCallback(
    (text: string, options: ConfirmOptions = {}) =>
      new Promise<boolean>((resolve) => setPending({ message: text, resolve, ...options })),
    [],
  );

  useEffect(() => {
    if (pending && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [pending]);

  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
    dialog.current?.close();
  };

  return (
    <FeedbackContext.Provider value={{ toast, confirm }}>
      {children}
      <div className="toast" role="status" aria-live="polite">
        {message && <span>{message}</span>}
      </div>
      <dialog ref={dialog} className="dialog" onCancel={(e) => { e.preventDefault(); close(false); }}>
        {pending && (
          <form method="dialog" className="form" onSubmit={(e) => { e.preventDefault(); close(true); }}>
            <p className="m-0">{pending.message}</p>
            <div className="button-row">
              <button type="submit" className={`button ${pending.danger ? 'danger' : 'primary'}`}>
                {pending.confirmLabel ?? t.common.confirm}
              </button>
              <button type="button" className="button" onClick={() => close(false)} autoFocus>
                {t.common.cancel}
              </button>
            </div>
          </form>
        )}
      </dialog>
    </FeedbackContext.Provider>
  );
}
