import { createContext, useContext } from 'react';

export interface ConfirmOptions {
  confirmLabel?: string;
  danger?: boolean;
}

export interface Feedback {
  /** Short confirmation after an action, announced to screen readers. */
  toast: (message: string) => void;
  /** Accessible replacement for window.confirm. */
  confirm: (message: string, options?: ConfirmOptions) => Promise<boolean>;
}

export const FeedbackContext = createContext<Feedback>({
  toast: () => undefined,
  confirm: async () => false,
});

export const useFeedback = () => useContext(FeedbackContext);
