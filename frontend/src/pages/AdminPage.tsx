import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { AdminGroup, AdminUser, InvitationCreated, InvitationRead, PlanInfo } from '../lib/types';
import { planName } from '../lib/plans';
import { useSession } from '../hooks/useSession';
import { useMeta } from '../hooks/useMeta';
import { useFormat } from '../hooks/useFormat';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { useOidcLabel } from '../hooks/useOidcLabel';
import { useI18n, useT } from '../i18n';

const USERS_KEY = ['admin', 'users'] as const;
const INVITATIONS_KEY = ['admin', 'invitations'] as const;
const GROUPS_KEY = ['admin', 'groups'] as const;

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
      <Groups />
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
  const provider = useOidcLabel();
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
  const unlink = useMutation({
    mutationFn: (user: AdminUser) => apiFetch<void>(`/v1/admin/users/${user.id}/oidc`, { method: 'DELETE' }),
    onSuccess: (_result, user) => {
      toast(a.oidcUnlinked(user.username));
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
  const removeLink = async (user: AdminUser) => {
    if (await confirm(a.oidcUnlinkConfirm(user.username, provider), { confirmLabel: a.oidcUnlink, danger: true })) {
      unlink.mutate(user);
    }
  };
  const del = async (user: AdminUser) => {
    if (await confirm(a.confirmDelete(user.username), { confirmLabel: a.delete, danger: true })) remove.mutate(user.id);
  };
  const state = queryState([users], !!users.data);
  const error = update.error ?? remove.error ?? createReset.error ?? unlink.error;
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
                    u.oidc_linked && a.signsInWith(provider),
                    u.has_password === false && a.noPassword,
                    a.groups(u.group_count),
                    u.last_seen_at ? a.lastSeen(f.date(u.last_seen_at)) : a.neverSeen,
                    u.deletion_due && a.deletionDue(f.date(u.deletion_due)),
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
                  {u.oidc_linked && (
                    <button type="button" className="button small" onClick={() => removeLink(u)}>{a.oidcUnlink}</button>
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

function Groups() {
  const t = useT();
  const a = t.admin;
  const f = useFormat();
  const { lang } = useI18n();
  const meta = useMeta();
  const [open, setOpen] = useState<number | null>(null);
  const groups = useQuery({ queryKey: GROUPS_KEY, queryFn: () => apiFetch<AdminGroup[]>('/v1/admin/groups') });
  const plans = meta.data?.plans ?? null;
  const name = (id: string) => planName(plans?.find((p) => p.id === id)?.name, lang) || id;
  const describePlan = (group: AdminGroup) => {
    if (!plans) return null;
    if (group.plan && !plans.some((p) => p.id === group.plan)) return a.planUnknown(group.plan);
    if (group.plan && group.plan !== group.effective_plan && group.plan_until) {
      return `${name(group.effective_plan)} (${a.planExpired(name(group.plan), f.date(group.plan_until))})`;
    }
    return group.plan_until ? `${name(group.effective_plan)} · ${t.group.planUntil(f.date(group.plan_until))}` : name(group.effective_plan);
  };
  const state = queryState([groups], !!groups.data);
  return (
    <section className="card" aria-labelledby="admin-groups-title">
      <h2 className="mt-0" id="admin-groups-title">{a.groupsTitle}</h2>
      <p className="subtle small mt-0">{a.groupsHint}</p>
      {state ?? (
        <ul className="list">
          {groups.data!.length === 0 && <li className="subtle">{a.noGroups}</li>}
          {groups.data!.map((g) => (
            <li key={g.id} className="row wrap">
              <span className="main">
                <span className="title">{g.name} <span className="subtle">#{g.id}</span></span>
                <div className="meta">
                  {[
                    describePlan(g),
                    a.groupSize(g.usage.members_per_group, g.usage.cars_per_group),
                    g.admins.length > 0 && a.groupAdmins(g.admins.map((admin) => admin.display_name).join(', ')),
                    g.last_activity_at && a.lastActivity(f.date(g.last_activity_at)),
                    g.plan_note,
                  ].filter(Boolean).join(' · ')}
                </div>
              </span>
              {plans && (
                <button type="button" className="button small" aria-expanded={open === g.id}
                  onClick={() => setOpen(open === g.id ? null : g.id)}>
                  {a.planEdit}
                </button>
              )}
              {plans && open === g.id && (
                <div className="panel">
                  <PlanEditor group={g} plans={plans} onDone={() => setOpen(null)} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PlanEditor({ group, plans, onDone }: { group: AdminGroup; plans: PlanInfo[]; onDone: () => void }) {
  const t = useT();
  const a = t.admin;
  const { lang } = useI18n();
  const meta = useMeta();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const defaultPlan = plans.find((p) => p.id === meta.data?.default_plan);
  const known = group.plan !== null && group.plan !== defaultPlan?.id && plans.some((p) => p.id === group.plan);
  const [plan, setPlan] = useState(known ? group.plan! : '');
  const [until, setUntil] = useState(group.plan_until ?? '');
  const [note, setNote] = useState(group.plan_note ?? '');
  const save = useMutation({
    mutationFn: () =>
      apiFetch<AdminGroup>(`/v1/admin/groups/${group.id}/plan`, {
        method: 'PUT',
        body: JSON.stringify({ plan: plan || null, until: plan && until ? until : null, note: note.trim() || null }),
      }),
    onSuccess: () => {
      toast(t.common.saved);
      void queryClient.invalidateQueries({ queryKey: GROUPS_KEY });
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const fieldId = `plan-${group.id}`;
  return (
    <form className="form" onSubmit={submit}>
      <div className="grid-2">
        <label className="field">
          <span>{a.plan}</span>
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            <option value="">{a.planDefault(planName(defaultPlan?.name, lang) || '…')}</option>
            {/* The default plan is the first option: a group without its own plan follows it */}
            {plans.filter((p) => p.id !== defaultPlan?.id).map((p) => (
              <option key={p.id} value={p.id}>{planName(p.name, lang)}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{a.planUntil}</span>
          <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} disabled={!plan}
            aria-describedby={`${fieldId}-until`} />
          <span id={`${fieldId}-until`} className="hint">{a.planUntilHint}</span>
        </label>
      </div>
      <label className="field">
        <span>{a.planNote}</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
      </label>
      {save.isError && <p className="error" role="alert">{errorText(save.error)}</p>}
      <span className="chips">
        <button type="submit" className="button primary small" disabled={save.isPending}>{t.common.save}</button>
        <button type="button" className="button small" onClick={onDone}>{t.common.cancel}</button>
      </span>
    </form>
  );
}
