import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
import { ME_KEY } from '../hooks/useMe';
import { APP_NAME } from '../app/brand';
import { useT } from '../i18n';
import { useMeta } from '../hooks/useMeta';
import { LegalLinks } from '../components/LegalLinks';
import { OidcButton } from '../components/OidcButton';
import { useCallbackParams } from '../hooks/useCallbackParams';
import { callbackErrorText } from '../lib/oidc';

export function LoginPage({ title = APP_NAME, notice }: { title?: string; notice?: string }) {
  const t = useT();
  const meta = useMeta();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // Coming back from the provider with an error (/login#error=oidc_no_account)
  const callback = useCallbackParams();
  const callbackError = callbackErrorText(callback.error);
  const passwords = meta.data?.password_login !== false;
  const oidc = !!meta.data?.oidc;
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
        {callbackError && <p className="error" role="alert">{callbackError}</p>}
        {passwords && <>
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
        </>}
        {oidc && passwords && <p className="subtle divider">{t.oidc.or}</p>}
        {oidc && <OidcButton action="login" primary={!passwords} body={() => ({ purpose: 'login' })} />}
        {meta.data?.mail && passwords && !notice && (
          <Link to="/forgot-password" className="link-button">{t.auth.forgotPassword}</Link>
        )}
        {meta.data?.registration === 'open' && !notice && (
          <p className="subtle m-0">{t.auth.noAccount} <Link to="/register">{t.auth.register}</Link></p>
        )}
        <LegalLinks />
      </form>
    </main>
  );
}
