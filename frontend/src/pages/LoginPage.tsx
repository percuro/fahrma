import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
import { ME_KEY } from '../hooks/useMe';
import { APP_NAME } from '../app/brand';
import { useT } from '../i18n';

export function LoginPage({ title = APP_NAME, notice }: { title?: string; notice?: string }) {
  const t = useT();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () =>
      apiFetch<Me>('/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
    onSuccess: (me) => queryClient.setQueryData(ME_KEY, me),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };

  return (
    <main className="center">
      <form className="card login" onSubmit={submit}>
        <h1>{title}</h1>
        {notice && <p className="notice m-0">{notice}</p>}
        <label className="field">
          <span>{t.auth.username}</span>
          <input name="username" autoComplete="username" autoCapitalize="none" required
            value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          <span>{t.auth.password}</span>
          <input name="password" type="password" autoComplete="current-password" required
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {login.isError && <p className="error" role="alert">{errorText(login.error)}</p>}
        <button type="submit" className="button primary" disabled={login.isPending}>
          {login.isPending ? t.auth.loggingIn : t.auth.login}
        </button>
      </form>
    </main>
  );
}
