import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import { useMeta } from '../hooks/useMeta';
import { useT } from '../i18n';
import { Loading } from '../components/Status';
import { LegalLinks } from '../components/LegalLinks';

/** Asks for a link by mail; the answer never tells whether the account or address exists. */
export function ForgotPasswordPage() {
  const t = useT();
  const fp = t.forgot;
  const meta = useMeta();
  const [login, setLogin] = useState('');
  const request = useMutation({
    mutationFn: () => apiFetch<void>('/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify({ login: login.trim() }) }),
  });
  if (meta.isPending) return <main className="center"><Loading /></main>;
  if (!meta.data?.mail) return <Navigate to="/" replace />;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    request.mutate();
  };
  return (
    <main className="center">
      <form className="card login" onSubmit={submit}>
        <h1>{fp.title}</h1>
        {request.isSuccess ? (
          <p className="m-0" role="status">{fp.sent}</p>
        ) : (
          <>
            <p className="subtle m-0">{fp.intro}</p>
            <label className="field">
              <span>{fp.login}</span>
              <input value={login} onChange={(e) => setLogin(e.target.value)} required maxLength={254}
                autoComplete="username" autoCapitalize="none" spellCheck={false} />
            </label>
            {request.isError && <p className="error" role="alert">{errorText(request.error)}</p>}
            <button type="submit" className="button primary" disabled={request.isPending}>{fp.submit}</button>
          </>
        )}
        <p className="subtle small m-0">{fp.noEmail}</p>
        <Link to="/" className="link-button">{fp.back}</Link>
        <LegalLinks />
      </form>
    </main>
  );
}
