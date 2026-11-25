import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me, RegistrationPending } from '../lib/types';
import { ME_KEY, useMe } from '../hooks/useMe';
import { useMeta } from '../hooks/useMeta';
import { useI18n, useT } from '../i18n';
import { Loading } from '../components/Status';
import { LegalLinks } from '../components/LegalLinks';
import { AccountFields } from '../components/AccountFields';
import { useAccountForm } from '../components/account-form';

/** Open registration (REGISTRATION=open): an account without a group. */
export function RegisterPage() {
  const t = useT();
  const { lang } = useI18n();
  const me = useMe();
  const meta = useMeta();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const form = useAccountForm();
  const [accept, setAccept] = useState(false);
  const [email, setEmail] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const register = useMutation({
    mutationFn: () =>
      apiFetch<Me | RegistrationPending>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ ...form.body(), locale: lang, accept_terms: accept, email: email.trim() || null }),
      }),
    onSuccess: (result) => {
      // With e-mail the account only exists once the link in the mail is used
      if (!('id' in result)) return setPending(result.email);
      queryClient.setQueryData(ME_KEY, result);
      navigate('/');
    },
  });

  if (me.isPending || meta.isPending) return <main className="center"><Loading /></main>;
  if (me.data) return <Navigate to="/" replace />;
  if (meta.data?.registration !== 'open') return <Navigate to="/" replace />;
  const termsUrl = meta.data.links.terms_url;
  if (pending) {
    return (
      <main className="center">
        <div className="card login">
          <h1>{t.register.checkMailTitle}</h1>
          <p className="m-0" role="status">{t.register.checkMail(pending)}</p>
          <Link to="/" className="link-button">{t.register.haveAccount}</Link>
        </div>
      </main>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.validate()) register.mutate();
  };
  const error = form.error || (register.isError ? errorText(register.error) : '');
  return (
    <main className="center">
      <form className="card login" onSubmit={submit}>
        <h1>{t.register.title}</h1>
        <p className="subtle m-0">{t.register.intro}</p>
        <AccountFields form={form} />
        {meta.data.mail && (
          <label className="field">
            <span>{t.register.email}</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" />
          </label>
        )}
        {termsUrl && (
          <label className="check">
            <input type="checkbox" checked={accept} required onChange={(e: ChangeEvent<HTMLInputElement>) => setAccept(e.target.checked)} />
            <span>
              {t.register.acceptTerms}{' '}
              <a href={termsUrl} target="_blank" rel="noopener noreferrer">{t.register.terms}</a>
            </span>
          </label>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="button primary" disabled={register.isPending}>{t.register.submit}</button>
        <Link to="/" className="link-button">{t.register.haveAccount}</Link>
        <LegalLinks />
      </form>
    </main>
  );
}
