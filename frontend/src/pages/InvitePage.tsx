import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { InvitationInfo, Me } from '../lib/types';
import { ME_KEY, useMe } from '../hooks/useMe';
import { useI18n, useT } from '../i18n';
import { Loading } from '../components/Status';
import { LegalLinks } from '../components/LegalLinks';
import { AccountFields } from '../components/AccountFields';
import { useAccountForm } from '../components/account-form';
import { LoginPage } from './LoginPage';

interface Accepted {
  kind: InvitationInfo['kind'];
  group_id: number | null;
}

/**
 * One page for every one-time link: PUBLIC_URL/invite#<token>.
 * The token is in the URL fragment, which browsers never send to the server.
 */
export function InvitePage() {
  const t = useT();
  const { hash } = useLocation();
  const token = decodeURIComponent(hash.replace(/^#/, ''));
  const me = useMe();
  const [haveAccount, setHaveAccount] = useState(false);
  const info = useQuery({
    queryKey: ['invite', token],
    queryFn: () => apiFetch<InvitationInfo>('/v1/invites/inspect', { method: 'POST', body: JSON.stringify({ token }) }),
    enabled: token.length > 0,
    retry: false,
    staleTime: Infinity,
  });

  if (token && (info.isPending || me.isPending)) return <main className="center"><Loading /></main>;
  if (!token || info.isError || !info.data) {
    return (
      <main className="center">
        <p role="alert">{info.isError ? errorText(info.error) : t.invite.invalid}</p>
        <Link to="/" className="button">{t.app.toStart}</Link>
      </main>
    );
  }
  const invitation = info.data;
  if (invitation.kind === 'password_reset') return <SetPassword token={token} username={invitation.username ?? ''} />;
  if (invitation.kind === 'signup') return <NewAccount token={token} title={t.invite.signupTitle} intro={t.invite.signupIntro} submit={t.invite.signupSubmit} />;
  if (invitation.kind === 'verify_email') return <VerifyEmail token={token} info={invitation} />;
  if (invitation.kind === 'registration') return <FinishRegistration token={token} info={invitation} />;
  const groupName = invitation.group_name ?? '';
  // A personal link takes over the place of a member without an account
  const member = invitation.member_name;
  if (me.data) return <Join token={token} groupName={groupName} member={member} me={me.data} />;
  if (haveAccount) return <LoginPage title={t.invite.loginToJoin(groupName)} />;
  return (
    <NewAccount token={token}
      title={member ? t.invite.titleAs(groupName, member) : t.invite.titleFor(groupName)}
      intro={member ? t.invite.createAccountAs(member) : t.invite.createAccount}
      submit={member ? t.invite.takeOverSubmit : t.invite.submit}
      initialName={member ?? ''}
      onHaveAccount={() => setHaveAccount(true)} />
  );
}

function useAccept(token: string, stay = false) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fields: Record<string, unknown>) =>
      apiFetch<Accepted>('/v1/invites/accept', { method: 'POST', body: JSON.stringify({ token, ...fields }) }),
    onSuccess: async ({ group_id }) => {
      // Leave the page first: asking about the used-up link again would count as a wrong token
      if (!stay) navigate(group_id ? `/g/${group_id}` : '/', { replace: true });
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
      if (!stay) queryClient.removeQueries({ queryKey: ['invite', token] });
    },
  });
}

function Join({ token, groupName, member, me }: { token: string; groupName: string; member: string | null; me: Me }) {
  const t = useT();
  const accept = useAccept(token);
  return (
    <main className="center">
      <div className="card login">
        <h1>{member ? t.invite.titleAs(groupName, member) : t.invite.title}</h1>
        <p>{member ? t.invite.takeOverQuestion(me.display_name, groupName, member) : t.invite.joinQuestion(me.display_name, groupName)}</p>
        {accept.isError && <p className="error" role="alert">{errorText(accept.error)}</p>}
        <button type="button" className="button primary" onClick={() => accept.mutate({})} disabled={accept.isPending}>
          {member ? t.invite.takeOver : t.invite.join}
        </button>
      </div>
    </main>
  );
}

/** Confirms an address; works without being logged in (the link itself is the proof). */
function VerifyEmail({ token, info }: { token: string; info: InvitationInfo }) {
  const t = useT();
  const accept = useAccept(token, true);
  return (
    <main className="center">
      <div className="card login">
        <h1>{t.invite.verifyTitle}</h1>
        {accept.isSuccess ? (
          <>
            <p className="m-0" role="status">{t.invite.verified(info.email ?? '')}</p>
            <Link to="/" className="button">{t.app.toStart}</Link>
          </>
        ) : (
          <>
            <p className="m-0">{t.invite.verifyIntro(info.email ?? '', info.username ?? '')}</p>
            {accept.isError && <p className="error" role="alert">{errorText(accept.error)}</p>}
            <button type="button" className="button primary" onClick={() => accept.mutate({})} disabled={accept.isPending}>
              {t.invite.verifySubmit}
            </button>
          </>
        )}
      </div>
    </main>
  );
}

function FinishRegistration({ token, info }: { token: string; info: InvitationInfo }) {
  const t = useT();
  const accept = useAccept(token);
  return (
    <main className="center">
      <div className="card login">
        <h1>{t.invite.registrationTitle}</h1>
        <p className="m-0">{t.invite.registrationIntro(info.username ?? '', info.email ?? '')}</p>
        {accept.isError && <p className="error" role="alert">{errorText(accept.error)}</p>}
        <button type="button" className="button primary" onClick={() => accept.mutate({})} disabled={accept.isPending}>
          {t.invite.registrationSubmit}
        </button>
        <LegalLinks />
      </div>
    </main>
  );
}

function NewAccount({ token, title, intro, submit, initialName = '', onHaveAccount }: {
  token: string;
  title: string;
  intro: string;
  submit: string;
  initialName?: string;
  onHaveAccount?: () => void;
}) {
  const t = useT();
  const { lang } = useI18n();
  const form = useAccountForm(initialName);
  const accept = useAccept(token);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (form.validate()) accept.mutate({ ...form.body(), locale: lang });
  };
  const error = form.error || (accept.isError ? errorText(accept.error) : '');
  return (
    <main className="center">
      <form className="card login" onSubmit={onSubmit}>
        <h1>{title}</h1>
        <p className="subtle m-0">{intro}</p>
        <AccountFields form={form} />
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="button primary" disabled={accept.isPending}>{submit}</button>
        {onHaveAccount && <button type="button" className="link-button" onClick={onHaveAccount}>{t.invite.haveAccount}</button>}
        <LegalLinks />
      </form>
    </main>
  );
}

function SetPassword({ token, username }: { token: string; username: string }) {
  const t = useT();
  const form = useAccountForm();
  const accept = useAccept(token);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (form.validate({ passwordOnly: true })) accept.mutate({ password: form.values.password });
  };
  const error = form.error || (accept.isError ? errorText(accept.error) : '');
  return (
    <main className="center">
      <form className="card login" onSubmit={onSubmit}>
        <h1>{t.invite.resetTitle}</h1>
        <p className="subtle m-0">{t.invite.resetIntro(username)}</p>
        <input type="text" name="username" value={username} autoComplete="username" readOnly hidden />
        <AccountFields form={form} passwordOnly passwordLabel={t.invite.newPassword} />
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="button primary" disabled={accept.isPending}>{t.invite.resetSubmit}</button>
      </form>
    </main>
  );
}

/** Links before 0.4 carried the token in the path (/invite/<token>, /einladung/<token>). */
export function LegacyInviteRedirect() {
  const { token } = useParams();
  return <Navigate to={{ pathname: '/invite', hash: token ?? '' }} replace />;
}
