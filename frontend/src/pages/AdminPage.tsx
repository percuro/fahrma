import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { AdminUser, InvitationCreated, InvitationRead } from '../lib/types';
import { useSession } from '../hooks/useSession';
import { useMeta } from '../hooks/useMeta';
import { useFormat } from '../hooks/useFormat';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { useT } from '../i18n';

const USERS_KEY = ['admin', 'users'] as const;
const INVITATIONS_KEY = ['admin', 'invitations'] as const;

/** Instance administration: accounts and invitations; never group contents. */
export function AdminPage() {
  const t = useT();
  const me = useSession();
  if (me.role !== 'admin') return <Navigate to="/profile" replace />;
  return (
    <>
      <h1>{t.admin.title}</h1>
      <p className="subtle">{t.admin.intro}</p>
      <Accounts />
      <Invitations />
    </>
  );
}

function CopyLink({ url }: { url: string }) {
  const a = useT().admin;
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Clipboard not allowed: the field stays selectable
    }
  };
  return (
    <div className="form">
      <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label={a.copy} />
      <button type="button" className="button small" onClick={copy}>{copied ? a.copied : a.copy}</button>
    </div>
  );
}

function Accounts() {
  const t = useT();
  const a = t.admin;
  const f = useFormat();
  const me = useSession();
  const { confirm, toast } = useFeedback();
  const queryClient = useQueryClient();
  const meta = useMeta();
  const users = useQuery({ queryKey: USERS_KEY, queryFn: () => apiFetch<AdminUser[]>('/v1/admin/users') });
  const [reset, setReset] = useState<{ user: AdminUser; link: InvitationCreated } | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin'] });
  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: number; role?: string; is_active?: boolean }) =>
      apiFetch<AdminUser>(`/v1/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => {
      toast(t.common.saved);
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiFetch<void>(`/v1/admin/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast(t.common.deleted);
      void refresh();
    },
  });
  const createReset = useMutation({
    mutationFn: ({ user, byMail }: { user: AdminUser; byMail: boolean }) =>
      apiFetch<InvitationCreated>(`/v1/admin/users/${user.id}/password-reset`, {
        method: 'POST',
        body: JSON.stringify({ send_email: byMail }),
      }),
    onSuccess: (link, { user }) => {
      setReset({ user, link });
      void refresh();
    },
  });
  const deactivate = async (user: AdminUser) => {
    if (await confirm(a.confirmDeactivate(user.username), { confirmLabel: a.deactivate, danger: true })) {
      update.mutate({ id: user.id, is_active: false });
    }
  };
  const del = async (user: AdminUser) => {
    if (await confirm(a.confirmDelete(user.username), { confirmLabel: a.delete, danger: true })) remove.mutate(user.id);
  };
  const state = queryState([users], !!users.data);
  const error = update.error ?? remove.error ?? createReset.error;
  return (
    <section className="card">
      <h2 className="mt-0">{a.accounts}</h2>
      {state ?? (
        <ul className="list">
          {users.data!.map((u) => (
            <li key={u.id} className="row wrap">
              <span className="main">
                <span className="title">{u.display_name}</span>
                <div className="meta">
                  {[
                    `@${u.username}`,
                    u.email,
                    u.role === 'admin' && a.adminRole,
                    !u.is_active && a.inactive,
                    a.groups(u.group_count),
                    u.last_seen_at ? a.lastSeen(f.date(u.last_seen_at)) : a.neverSeen,
                  ].filter(Boolean).join(' · ')}
                </div>
              </span>
              {u.id !== me.id && (
                <span className="chips">
                  <button type="button" className="button small"
                    onClick={() => update.mutate({ id: u.id, role: u.role === 'admin' ? 'user' : 'admin' })}>
                    {u.role === 'admin' ? a.revokeAdmin : a.makeAdmin}
                  </button>
                  {u.is_active ? (
                    <button type="button" className="button small" onClick={() => deactivate(u)}>{a.deactivate}</button>
                  ) : (
                    <button type="button" className="button small" onClick={() => update.mutate({ id: u.id, is_active: true })}>{a.reactivate}</button>
                  )}
                  {u.is_active && (
                    <button type="button" className="button small" onClick={() => createReset.mutate({ user: u, byMail: false })}>
                      {a.resetLink}
                    </button>
                  )}
                  {u.is_active && u.email && meta.data?.mail && (
                    <button type="button" className="button small" onClick={() => createReset.mutate({ user: u, byMail: true })}>
                      {a.resetByMail}
                    </button>
                  )}
                  <button type="button" className="button small danger" onClick={() => del(u)}>{a.delete}</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {reset && (
        <div className="mt-1">
          <p className="m-0" role="status">
            {reset.link.email_sent && reset.user.email
              ? a.resetSent(reset.user.username, reset.user.email)
              : a.resetCreated(reset.user.username)}
          </p>
          <CopyLink url={reset.link.url} />
        </div>
      )}
      {error && <p className="error" role="alert">{errorText(error)}</p>}
    </section>
  );
}

function Invitations() {
  const t = useT();
  const a = t.admin;
  const f = useFormat();
  const queryClient = useQueryClient();
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [note, setNote] = useState('');
  const [email, setEmail] = useState('');
  const meta = useMeta();
  const invitations = useQuery({
    queryKey: INVITATIONS_KEY,
    queryFn: () => apiFetch<InvitationRead[]>('/v1/admin/invitations'),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: INVITATIONS_KEY });
  const create = useMutation({
    mutationFn: (to: string | null) =>
      apiFetch<InvitationCreated>('/v1/admin/invitations', {
        method: 'POST',
        body: JSON.stringify({ role, note: note.trim() || null, email: to }),
      }),
    onSuccess: () => {
      setNote('');
      setEmail('');
      void refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => apiFetch<void>(`/v1/admin/invitations/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(email.trim() || null);
  };
  const state = queryState([invitations], !!invitations.data);
  return (
    <section className="card">
      <h2 className="mt-0">{a.invitations}</h2>
      <p className="subtle small mt-0">{a.invitationsHint}</p>
      <form className="form" onSubmit={submit}>
        <div className="grid-2">
          <label className="field">
            <span>{a.note}</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={80} />
          </label>
          <label className="field">
            <span>{a.role}</span>
            <select value={role} onChange={(e) => setRole(e.target.value as 'user' | 'admin')}>
              <option value="user">{a.roleUser}</option>
              <option value="admin">{a.roleAdmin}</option>
            </select>
          </label>
        </div>
        {meta.data?.mail && (
          <label className="field">
            <span>{a.sendTo}</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="off" />
          </label>
        )}
        <button type="submit" className="button primary" disabled={create.isPending}>{a.createInvitation}</button>
      </form>
      {create.data && (
        <div className="mt-1">
          {create.data.email_sent && create.variables && <p className="m-0" role="status">{a.sentTo(create.variables)}</p>}
          <CopyLink url={create.data.url} />
          <p className="subtle small m-0">{a.validUntil(f.date(create.data.expires_at))}</p>
        </div>
      )}
      <h3>{a.openInvitations}</h3>
      {state ?? (
        <ul className="list">
          {invitations.data!.length === 0 && <li className="subtle">{a.noInvitations}</li>}
          {invitations.data!.map((i) => (
            <li key={i.id} className="row wrap">
              <span className="main">
                <span className="title">
                  {i.purpose === 'password_reset' ? `${a.passwordReset} @${i.target_username ?? '?'}` : (i.note ?? a.signup)}
                </span>
                <div className="meta">
                  {[i.role === 'admin' && a.adminRole, i.email, a.validUntil(f.date(i.expires_at))].filter(Boolean).join(' · ')}
                </div>
              </span>
              <button type="button" className="button small" onClick={() => revoke.mutate(i.id)} disabled={revoke.isPending}>
                {a.revoke}
              </button>
            </li>
          ))}
        </ul>
      )}
      {(create.isError || revoke.isError) && <p className="error" role="alert">{errorText(create.error ?? revoke.error)}</p>}
    </section>
  );
}
