import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
import { ME_KEY, useMe } from '../hooks/useMe';
import { useT } from '../i18n';
import { Loading } from '../components/Status';
import { LoginPage } from './LoginPage';

export function InvitePage() {
  const t = useT();
  const { token = '' } = useParams();
  const me = useMe();
  const [haveAccount, setHaveAccount] = useState(false);
  const invite = useQuery({
    queryKey: ['invite', token],
    queryFn: () => apiFetch<{ group_name: string; valid: boolean }>(`/v1/invites/${encodeURIComponent(token)}`),
  });

  if (invite.isPending || me.isPending) return <main className="center"><Loading /></main>;
  if (invite.isError || !invite.data?.valid) {
    return (
      <main className="center">
        <p role="alert">{t.invite.invalid}</p>
        <Link to="/" className="button">{t.app.toStart}</Link>
      </main>
    );
  }
  const groupName = invite.data.group_name;
  if (me.data) return <Accept token={token} groupName={groupName} me={me.data} />;
  if (haveAccount) return <LoginPage title={t.invite.loginToJoin(groupName)} />;
  return <Register token={token} groupName={groupName} onHaveAccount={() => setHaveAccount(true)} />;
}

function Accept({ token, groupName, me }: { token: string; groupName: string; me: Me }) {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const accept = useMutation({
    mutationFn: () => apiFetch<{ group_id: number }>(`/v1/invites/${encodeURIComponent(token)}/accept`, { method: 'POST' }),
    onSuccess: async ({ group_id }) => {
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
      navigate(`/g/${group_id}`);
    },
  });
  return (
    <main className="center">
      <div className="card login">
        <h1>{t.invite.title}</h1>
        <p>{t.invite.joinQuestion(me.display_name, groupName)}</p>
        {accept.isError && <p className="error" role="alert">{errorText(accept.error)}</p>}
        <button type="button" className="button primary" onClick={() => accept.mutate()} disabled={accept.isPending}>
          {t.invite.join}
        </button>
      </div>
    </main>
  );
}

function Register({ token, groupName, onHaveAccount }: { token: string; groupName: string; onHaveAccount: () => void }) {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ username: '', display_name: '', password: '', repeat: '' });
  const [localError, setLocalError] = useState('');
  const register = useMutation({
    mutationFn: () =>
      apiFetch<Me>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ token, username: form.username, display_name: form.display_name, password: form.password }),
      }),
    onSuccess: (me) => {
      queryClient.setQueryData(ME_KEY, me);
      navigate(me.groups.length ? `/g/${me.groups[0].id}` : '/');
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.password.length < 12) return setLocalError(t.auth.passwordTooShort);
    if (form.password !== form.repeat) return setLocalError(t.auth.passwordMismatch);
    setLocalError('');
    register.mutate();
  };
  const set = (key: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });
  const error = localError || (register.isError ? errorText(register.error) : '');
  return (
    <main className="center">
      <form className="card login" onSubmit={submit}>
        <h1>{t.invite.titleFor(groupName)}</h1>
        <p className="subtle m-0">{t.invite.createAccount}</p>
        <label className="field">
          <span>{t.invite.displayName}</span>
          <input value={form.display_name} onChange={set('display_name')} required maxLength={80} autoComplete="given-name" />
        </label>
        <label className="field">
          <span>{t.invite.username}</span>
          <input value={form.username} onChange={set('username')} required minLength={2} maxLength={80}
            pattern="[A-Za-z0-9._\-]+" title={t.auth.usernameHint} autoCapitalize="none" autoComplete="username" />
        </label>
        <label className="field">
          <span>{t.invite.password}</span>
          <input type="password" value={form.password} onChange={set('password')} required autoComplete="new-password" />
        </label>
        <label className="field">
          <span>{t.auth.passwordRepeat}</span>
          <input type="password" value={form.repeat} onChange={set('repeat')} required autoComplete="new-password" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="button primary" disabled={register.isPending}>{t.invite.submit}</button>
        <button type="button" className="link-button" onClick={onHaveAccount}>{t.invite.haveAccount}</button>
      </form>
    </main>
  );
}

/** Invitation links from 0.1 used a German path (/einladung/…). */
export function LegacyInviteRedirect() {
  const { token } = useParams();
  return <Navigate to={`/invite/${token ?? ''}`} replace />;
}
