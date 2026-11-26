import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiUrl, errorText } from '../lib/api';
import type { DeletionPreview, DeviceSession, NotificationsState, NotifySettings } from '../lib/types';
import { PushError, pushSupport, subscribe, unsubscribe } from '../lib/push';
import { ME_KEY } from '../hooks/useMe';
import { useFormat } from '../hooks/useFormat';
import { useMeta } from '../hooks/useMeta';
import { useSession } from '../hooks/useSession';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { useI18n, useT } from '../i18n';

export function ChangePassword() {
  const t = useT();
  const a = t.account;
  const { toast } = useFeedback();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [localError, setLocalError] = useState('');
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: () =>
      apiFetch<void>('/v1/account/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      }),
    onSuccess: () => {
      setCurrent('');
      setNext('');
      setRepeat('');
      toast(a.passwordChanged);
      void queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (next.length < 12) return setLocalError(t.auth.passwordTooShort);
    if (next !== repeat) return setLocalError(t.auth.passwordMismatch);
    setLocalError('');
    change.mutate();
  };
  const error = localError || (change.isError ? errorText(change.error) : '');
  return (
    <details className="card">
      <summary><h2 className="inline">{a.password}</h2></summary>
      <form className="form mt-1" onSubmit={submit}>
        <label className="field">
          <span>{a.currentPassword}</span>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
        </label>
        <label className="field">
          <span>{a.newPassword}</span>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} required autoComplete="new-password" />
        </label>
        <label className="field">
          <span>{t.auth.passwordRepeat}</span>
          <input type="password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required autoComplete="new-password" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="button" disabled={change.isPending}>{t.common.save}</button>
      </form>
    </details>
  );
}

export function Devices() {
  const t = useT();
  const a = t.account;
  const f = useFormat();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const sessions = useQuery({
    queryKey: ['sessions'],
    queryFn: () => apiFetch<DeviceSession[]>('/v1/account/sessions'),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['sessions'] });
  const revoke = useMutation({
    mutationFn: (id: number) => apiFetch<void>(`/v1/account/sessions/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  });
  const revokeOthers = useMutation({
    mutationFn: () => apiFetch<void>('/v1/account/sessions/revoke-others', { method: 'POST' }),
    onSuccess: () => {
      toast(a.signedOutOthers);
      void refresh();
    },
  });
  const state = queryState([sessions], !!sessions.data);
  const others = sessions.data?.filter((s) => !s.current).length ?? 0;
  return (
    <section className="card">
      <h2 className="mt-0">{a.devices}</h2>
      {state ?? (
        <ul className="list">
          {sessions.data!.map((s) => (
            <li key={s.id} className="row wrap">
              <span className="main">
                <span className="title">{s.device ?? a.unknownDevice}</span>
                <div className="meta">
                  {[s.current && a.thisDevice, a.lastSeen(f.date(s.last_seen_at ?? s.created_at))].filter(Boolean).join(' · ')}
                </div>
              </span>
              {!s.current && (
                <button type="button" className="button small" onClick={() => revoke.mutate(s.id)} disabled={revoke.isPending}>
                  {a.signOutDevice}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {others > 1 && (
        <button type="button" className="button" onClick={() => revokeOthers.mutate()} disabled={revokeOthers.isPending}>
          {a.signOutOthers}
        </button>
      )}
      {(revoke.isError || revokeOthers.isError) && (
        <p className="error" role="alert">{errorText(revoke.error ?? revokeOthers.error)}</p>
      )}
    </section>
  );
}

export function MyData() {
  const a = useT().account;
  const meta = useMeta();
  const me = useSession();
  const months = meta.data?.inactive_delete_months;
  // Instance admins are never deleted for being unused
  const inactive = months && me.role !== 'admin'
    ? `${a.inactiveRule(months)} ${!meta.data?.mail ? a.inactiveNoMail : me.email ? a.inactiveWarnMail : a.inactiveAddMail}`
    : null;
  return (
    <section>
      <h2>{a.myData}</h2>
      <p className="subtle small">{a.myDataHint}</p>
      {inactive && <p className="subtle small">{inactive}</p>}
      <p><a className="button" href={apiUrl('/v1/account/export.json')} download>{a.download}</a></p>
    </section>
  );
}

export function DeleteAccount() {
  const t = useT();
  const a = t.account;
  const { confirm } = useFeedback();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const preview = useQuery({
    queryKey: ['deletion-preview'],
    queryFn: () => apiFetch<DeletionPreview>('/v1/account/deletion-preview'),
    enabled: open,
  });
  const remove = useMutation({
    mutationFn: () => apiFetch<void>('/v1/account', { method: 'DELETE', body: JSON.stringify({ password }) }),
    onSuccess: () => {
      window.dispatchEvent(new Event('carshare:logout'));
      queryClient.clear();
      queryClient.setQueryData(ME_KEY, null);
      navigate('/', { replace: true });
    },
  });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (await confirm(a.deleteConfirm, { confirmLabel: a.deleteSubmit, danger: true })) remove.mutate();
  };
  return (
    <details className="card danger-zone" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary><h2 className="inline">{a.deleteTitle}</h2></summary>
      <form className="form mt-1" onSubmit={submit}>
        <p className="m-0">{a.deleteIntro}</p>
        {preview.data && preview.data.groups_deleted.length > 0 && (
          <p className="m-0">{a.deleteGroups(preview.data.groups_deleted.map((g) => g.name).join(', '))}</p>
        )}
        {preview.data?.admin_handover.map((h) => (
          <p key={h.group_id} className="m-0">{a.deleteHandover(h.group_name, h.new_admin_name)}</p>
        ))}
        <label className="field">
          <span>{a.deleteConfirmPassword}</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        {remove.isError && <p className="error" role="alert">{errorText(remove.error)}</p>}
        <button type="submit" className="button primary danger" disabled={remove.isPending || !password}>{a.deleteSubmit}</button>
      </form>
    </details>
  );
}

/** The confirmed address (for "forgot password"), one waiting for confirmation, and changing it. */
export function EmailAddress() {
  const t = useT();
  const a = t.account;
  const me = useSession();
  const meta = useMeta();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const refresh = () => queryClient.invalidateQueries({ queryKey: ME_KEY });
  const change = useMutation({
    mutationFn: () =>
      apiFetch<void>('/v1/account/email', { method: 'POST', body: JSON.stringify({ email: email.trim(), password }) }),
    onSuccess: () => {
      setEmail('');
      setPassword('');
      toast(a.emailSent);
      void refresh();
    },
  });
  const cancel = useMutation({
    mutationFn: () => apiFetch<void>('/v1/account/email/pending', { method: 'DELETE' }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => apiFetch<void>('/v1/account/email', { method: 'DELETE', body: JSON.stringify({ password }) }),
    onSuccess: () => {
      setPassword('');
      toast(a.emailRemoved);
      void refresh();
    },
  });
  // Without e-mail on the instance an address is useless; an old one can still be removed
  if (!meta.data?.mail && !me.email) return null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate();
  };
  const error = change.error ?? cancel.error ?? remove.error;
  return (
    <details className="card" open={!!me.email_pending || undefined}>
      <summary><h2 className="inline">{a.email}</h2></summary>
      <div className="form mt-1">
        <p className="subtle small m-0">{a.emailHint}</p>
        <p className="m-0">{me.email ? a.emailCurrent(me.email) : a.emailNone}</p>
        {me.email_pending && (
          <div className="button-row mt-0">
            <p className="m-0" role="status">{a.emailPending(me.email_pending)}</p>
            <button type="button" className="button small" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              {a.emailCancel}
            </button>
          </div>
        )}
        <form className="form" onSubmit={submit}>
          {meta.data?.mail && (
            <label className="field">
              <span>{a.emailNew}</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="email" />
            </label>
          )}
          <label className="field">
            <span>{a.confirmPassword}</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          </label>
          {error && <p className="error" role="alert">{errorText(error)}</p>}
          <div className="button-row mt-0">
            {meta.data?.mail && (
              <button type="submit" className="button primary" disabled={change.isPending || !email.trim()}>{a.emailSend}</button>
            )}
            {me.email && (
              <button type="button" className="button" onClick={() => remove.mutate()} disabled={remove.isPending || !password}>
                {a.emailRemove}
              </button>
            )}
          </div>
        </form>
      </div>
    </details>
  );
}

const NOTIFICATIONS_KEY = ['notifications'] as const;

/** Push notifications: on this device, and which ones (for every device of the account). */
export function Notifications() {
  const t = useT();
  const n = t.notifications;
  const { lang } = useI18n();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const meta = useMeta();
  const vapidKey = meta.data?.vapid_public_key ?? null;
  const state = useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => apiFetch<NotificationsState>('/v1/account/notifications'),
    enabled: vapidKey !== null,
  });
  const support = pushSupport();
  const [problem, setProblem] = useState('');
  const describe = (error: unknown) =>
    error instanceof PushError ? (error.reason === 'denied' ? n.blocked : n.noWorker) : errorText(error);

  const toggle = useMutation({
    mutationFn: async (on: boolean): Promise<NotificationsState | null> => {
      if (on) return subscribe(vapidKey!, lang);
      await unsubscribe();
      return null;
    },
    onMutate: () => setProblem(''),
    onSuccess: (data, on) => {
      if (data) queryClient.setQueryData(NOTIFICATIONS_KEY, data);
      else void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
      toast(on ? n.on : n.off);
    },
    onError: (error) => setProblem(describe(error)),
  });
  const save = useMutation({
    mutationFn: (settings: NotifySettings) =>
      apiFetch<NotificationsState>('/v1/account/notifications', { method: 'PUT', body: JSON.stringify(settings) }),
    // The switch moves at once; a refusal puts it back
    onMutate: (settings) => {
      setProblem('');
      queryClient.setQueryData<NotificationsState>(NOTIFICATIONS_KEY, (old) => (old ? { ...old, settings } : old));
    },
    onSuccess: (data) => {
      queryClient.setQueryData(NOTIFICATIONS_KEY, data);
      toast(t.common.saved);
    },
    onError: (error) => {
      setProblem(describe(error));
      void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
  const test = useMutation({
    mutationFn: () => apiFetch<void>('/v1/account/push-test', { method: 'POST' }),
    onSuccess: () => toast(n.testSent),
    onError: (error) => setProblem(describe(error)),
  });

  if (vapidKey === null) return null;
  const data = state.data;
  const settings = data?.settings;
  const change = (patch: Partial<NotifySettings>) => settings && save.mutate({ ...settings, ...patch });
  const others = data ? data.devices - (data.this_device ? 1 : 0) : 0;
  const blocked = support === 'supported' && Notification.permission === 'denied';

  return (
    <section className="card">
      <h2 className="mt-0">{n.title}</h2>
      {queryState([state], !!data) ?? (
        <div className="form">
          {support === 'supported' ? (
            <>
              <label className="check">
                <input type="checkbox" checked={data!.this_device} disabled={toggle.isPending}
                  onChange={(e) => toggle.mutate(e.target.checked)} />
                {n.thisDevice}
              </label>
              <p className="subtle small m-0">{n.thisDeviceHint}</p>
              {blocked && !data!.this_device && <p className="notice m-0">{n.blocked}</p>}
            </>
          ) : (
            <p className="notice m-0">{support === 'install-first' ? n.installFirst : n.unsupported}</p>
          )}
          {others > 0 && <p className="subtle small m-0">{n.otherDevices(others)}</p>}
          <fieldset className="form plain">
            <legend className="title">{n.which}</legend>
            <p className="subtle small m-0">{n.whichHint}</p>
            <label className="check">
              <input type="checkbox" checked={settings!.reservation_reminder}
                onChange={(e) => change({ reservation_reminder: e.target.checked })} />
              {n.reminder}
            </label>
            {settings!.reservation_reminder && (
              <label className="field">
                <span>{n.lead}</span>
                <select value={settings!.lead_minutes}
                  onChange={(e) => change({ lead_minutes: Number(e.target.value) as NotifySettings['lead_minutes'] })}>
                  {[15, 60, 180].map((m) => <option key={m} value={m}>{n.leadOption(m)}</option>)}
                </select>
              </label>
            )}
            <label className="check">
              <input type="checkbox" checked={settings!.reservation_changes}
                onChange={(e) => change({ reservation_changes: e.target.checked })} />
              {n.changes}
            </label>
            <label className="check">
              <input type="checkbox" checked={settings!.open_trip} onChange={(e) => change({ open_trip: e.target.checked })} />
              {n.openTrip}
            </label>
            <label className="check">
              <input type="checkbox" checked={settings!.settlements} onChange={(e) => change({ settlements: e.target.checked })} />
              {n.settlements}
            </label>
          </fieldset>
          {problem && <p className="error" role="alert">{problem}</p>}
          {data!.this_device && (
            <div className="button-row">
              <button type="button" className="button" onClick={() => test.mutate()} disabled={test.isPending}>{n.test}</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
