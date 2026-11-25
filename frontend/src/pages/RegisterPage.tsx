import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
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
  const register = useMutation({
    mutationFn: () =>
      apiFetch<Me>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ ...form.body(), locale: lang, accept_terms: accept }),
      }),
    onSuccess: (account) => {
      queryClient.setQueryData(ME_KEY, account);
      navigate('/');
    },
  });

  if (me.isPending || meta.isPending) return <main className="center"><Loading /></main>;
  if (me.data) return <Navigate to="/" replace />;
  if (meta.data?.registration !== 'open') return <Navigate to="/" replace />;
  const termsUrl = meta.data.links.terms_url;

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
