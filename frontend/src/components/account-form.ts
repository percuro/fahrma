import { useState, type ChangeEvent } from 'react';
import { useT } from '../i18n';

const USERNAME = /^[a-z0-9._-]{3,32}$/;

export interface AccountForm {
  values: { username: string; display_name: string; password: string; repeat: string };
  set: (key: keyof AccountForm['values']) => (event: ChangeEvent<HTMLInputElement>) => void;
  error: string;
  /** Checks the input in the browser; returns false and shows a message if something is wrong. */
  validate: (options?: { passwordOnly?: boolean; withoutPassword?: boolean }) => boolean;
  body: () => { username: string; display_name: string | null; password: string };
}

export function useAccountForm(initialDisplayName = ''): AccountForm {
  const t = useT();
  const [values, setValues] = useState({ username: '', display_name: initialDisplayName, password: '', repeat: '' });
  const [error, setError] = useState('');
  return {
    values,
    error,
    set: (key) => (event) => setValues((current) => ({ ...current, [key]: event.target.value })),
    validate: ({ passwordOnly = false, withoutPassword = false } = {}) => {
      let message = '';
      if (!passwordOnly && !USERNAME.test(values.username.trim().toLowerCase())) message = t.errors.username_invalid({});
      // Through the OIDC provider: name and username only
      else if (withoutPassword) message = '';
      else if (values.password.length < 12) message = t.auth.passwordTooShort;
      else if (values.password !== values.repeat) message = t.auth.passwordMismatch;
      setError(message);
      return !message;
    },
    body: () => ({
      username: values.username.trim().toLowerCase(),
      display_name: values.display_name.trim() || null,
      password: values.password,
    }),
  };
}
