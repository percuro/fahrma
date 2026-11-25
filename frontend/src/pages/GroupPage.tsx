import { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiFetch, apiUrl, errorText } from '../lib/api';
import { parseKm } from '../lib/format';
import type { Car, EnergyUnit, Group, GroupInviteCreated, Member } from '../lib/types';
import { useAudit, useCars, useGroup, useGroupId, useGroupMutation, useMemberNames } from '../hooks/useGroupData';
import { ME_KEY } from '../hooks/useMe';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useI18n, useT } from '../i18n';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { LinkBox } from '../components/LinkBox';
import { useMeta } from '../hooks/useMeta';

const COMMON_CURRENCIES = ['EUR', 'CHF', 'GBP', 'USD', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF'];

export function GroupPage() {
  const group = useGroup();
  const state = queryState([group], !!group.data);
  if (state) return state;
  const data = group.data!;
  const isAdmin = data.my_role === 'admin';
  return (
    <>
      <h1>{data.name}</h1>
      <Members />
      {isAdmin && <Invite />}
      <Cars isAdmin={isAdmin} />
      {isAdmin && <GroupSettings group={data} />}
      <DataExport />
      <AuditLog />
      {isAdmin && <DeleteGroup group={data} />}
    </>
  );
}

function Members() {
  const t = useT();
  const g = t.group;
  const f = useFormat();
  const { confirm, toast } = useFeedback();
  const group = useGroup();
  const me = useSession();
  const [open, setOpen] = useState<{ userId: number; mode: 'link' | 'rename' } | null>(null);
  const update = useGroupMutation<{ userId: number; role?: string; active?: boolean }>(
    'PATCH', ({ userId }) => `/members/${userId}`, ({ role, active }) => ({ role, active }),
  );
  const isAdmin = group.data?.my_role === 'admin';
  const toggleActive = async (userId: number, name: string, active: boolean) => {
    if (active && !(await confirm(g.confirmRemove(name), { confirmLabel: g.removeMember, danger: true }))) return;
    update.mutate({ userId, active: !active }, { onSuccess: () => toast(t.common.saved) });
  };
  const describe = (m: Member) => {
    if (m.deleted) return [g.deletedAccount];
    return [
      m.placeholder ? g.withoutAccount : `@${m.username}`,
      m.role === 'admin' && g.admin,
      !m.active && g.left,
      m.link_expires_at && g.linkOpen(f.date(m.link_expires_at)),
    ];
  };
  return (
    <section className="card">
      <h2 className="mt-0">{g.members}</h2>
      <ul className="list">
        {group.data?.members.map((m) => (
          <li key={m.user_id} className="row wrap">
            <span className="main">
              <span className="title">{m.display_name}</span>
              <div className="meta">{describe(m).filter(Boolean).join(' · ')}</div>
            </span>
            {isAdmin && m.user_id !== me.id && !m.deleted && (
              <span className="chips">
                {m.placeholder ? (
                  <>
                    {m.active && (
                      <button type="button" className="button small" aria-expanded={open?.userId === m.user_id && open.mode === 'link'}
                        onClick={() => setOpen({ userId: m.user_id, mode: 'link' })}>
                        {g.personalLink}
                      </button>
                    )}
                    <button type="button" className="button small" aria-expanded={open?.userId === m.user_id && open.mode === 'rename'}
                      onClick={() => setOpen({ userId: m.user_id, mode: 'rename' })}>
                      {g.renameMember}
                    </button>
                  </>
                ) : (
                  <button type="button" className="button small"
                    onClick={() => update.mutate({ userId: m.user_id, role: m.role === 'admin' ? 'member' : 'admin' })}>
                    {m.role === 'admin' ? g.revokeAdmin : g.makeAdmin}
                  </button>
                )}
                <button type="button" className="button small" onClick={() => toggleActive(m.user_id, m.display_name, m.active)}>
                  {m.active ? g.removeMember : g.readdMember}
                </button>
              </span>
            )}
            {open?.userId === m.user_id && (
              <div className="panel">
                {open.mode === 'link'
                  ? <PersonalLink member={m} onClose={() => setOpen(null)} />
                  : <RenameMember member={m} onDone={() => setOpen(null)} />}
              </div>
            )}
          </li>
        ))}
      </ul>
      {update.isError && <p className="error" role="alert">{errorText(update.error)}</p>}
      {isAdmin && <AddPerson />}
    </section>
  );
}

/** Link with an optional e-mail address; used for group invitations and personal links. */
function LinkCreator({ path, label, button, hint, onClose }: {
  path: string;
  label: string;
  button: string;
  hint?: string;
  onClose?: () => void;
}) {
  const t = useT();
  const g = t.group;
  const meta = useMeta();
  const [email, setEmail] = useState('');
  const create = useGroupMutation<{ email: string | null }, GroupInviteCreated>('POST', () => path, (v) => v);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate({ email: email.trim() || null });
  };
  const sentTo = create.data?.email_sent ? create.variables?.email : null;
  return (
    <div className="form">
      {hint && <p className="subtle small m-0">{hint}</p>}
      {create.data ? (
        <LinkBox url={create.data.url} expiresAt={create.data.expires_at} sentTo={sentTo} label={label}
          onNew={() => { create.reset(); setEmail(''); }} />
      ) : (
        <form className="form" onSubmit={submit}>
          {meta.data?.mail && (
            <label className="field">
              <span>{g.sendTo}</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="off" />
            </label>
          )}
          <div className="button-row mt-0">
            <button type="submit" className="button primary" disabled={create.isPending}>{button}</button>
            {onClose && <button type="button" className="button" onClick={onClose}>{t.common.cancel}</button>}
          </div>
        </form>
      )}
      {create.data && onClose && <button type="button" className="link-button" onClick={onClose}>{g.close}</button>}
      {create.isError && <p className="error" role="alert">{errorText(create.error)}</p>}
    </div>
  );
}

function PersonalLink({ member, onClose }: { member: Member; onClose: () => void }) {
  const g = useT().group;
  return (
    <LinkCreator path={`/members/${member.user_id}/invite`} label={g.personalLink} button={g.createInvite}
      hint={g.personalLinkHint(member.display_name)} onClose={onClose} />
  );
}

function RenameMember({ member, onDone }: { member: Member; onDone: () => void }) {
  const t = useT();
  const { toast } = useFeedback();
  const [name, setName] = useState(member.display_name);
  const rename = useGroupMutation<string>('PATCH', () => `/members/${member.user_id}`, (display_name) => ({ display_name }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    rename.mutate(name.trim(), {
      onSuccess: () => {
        toast(t.common.saved);
        onDone();
      },
    });
  };
  return (
    <form className="form" onSubmit={submit}>
      <label className="field">
        <span>{t.common.name}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} autoFocus />
      </label>
      {rename.isError && <p className="error" role="alert">{errorText(rename.error)}</p>}
      <div className="button-row mt-0">
        <button type="submit" className="button primary" disabled={rename.isPending || !name.trim()}>{t.common.save}</button>
        <button type="button" className="button" onClick={onDone}>{t.common.cancel}</button>
      </div>
    </form>
  );
}

function AddPerson() {
  const t = useT();
  const g = t.group;
  const { toast } = useFeedback();
  const [name, setName] = useState('');
  const add = useGroupMutation<string>('POST', () => '/members', (display_name) => ({ display_name }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate(name.trim(), {
      onSuccess: () => {
        setName('');
        toast(t.common.saved);
      },
    });
  };
  return (
    <details className="mt-1">
      <summary className="link-button">{g.addPerson}</summary>
      <form className="form mt-1" onSubmit={submit}>
        <p className="subtle small m-0">{g.addPersonHint}</p>
        <label className="field">
          <span>{t.common.name}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
        </label>
        {add.isError && <p className="error" role="alert">{errorText(add.error)}</p>}
        <button type="submit" className="button" disabled={add.isPending || !name.trim()}>{g.add}</button>
      </form>
    </details>
  );
}

function Invite() {
  const g = useT().group;
  return (
    <section className="card">
      <h2 className="mt-0">{g.invite}</h2>
      <LinkCreator path="/invites" label={g.inviteLink} button={g.createInvite} hint={g.inviteHint} />
    </section>
  );
}

function Cars({ isAdmin }: { isAdmin: boolean }) {
  const t = useT();
  const g = t.group;
  const f = useFormat();
  const cars = useCars();
  const [editing, setEditing] = useState<Car | 'new' | null>(null);
  return (
    <section className="card">
      <h2 className="mt-0">{g.cars}</h2>
      {cars.isError && queryState([cars], false)}
      <ul className="list">
        {cars.data?.map((c) => (
          <li key={c.id} className="row">
            <span className="main">
              <span className="title">{c.name}{c.plate ? ` · ${c.plate}` : ''}</span>
              <div className="meta">
                {[g.current(f.km(c.last_km)), c.energy_unit === 'kWh' ? t.car.electric : t.car.combustion, c.archived && g.archived]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </span>
            {isAdmin && <button type="button" className="button small" onClick={() => setEditing(c)}>{t.common.edit}</button>}
          </li>
        ))}
        {cars.data?.length === 0 && <li className="subtle">{g.noCars}</li>}
      </ul>
      {isAdmin && editing === null && <button type="button" className="button" onClick={() => setEditing('new')}>{g.addCar}</button>}
      {editing !== null && (
        <CarForm key={editing === 'new' ? 'new' : editing.id} car={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
      )}
    </section>
  );
}

function CarForm({ car, onDone }: { car?: Car; onDone: () => void }) {
  const t = useT();
  const c = t.car;
  const { toast } = useFeedback();
  const [name, setName] = useState(car?.name ?? '');
  const [plate, setPlate] = useState(car?.plate ?? '');
  const [startKm, setStartKm] = useState(car ? String(car.start_odometer_km) : '');
  const [energy, setEnergy] = useState<EnergyUnit>(car?.energy_unit ?? 'l');
  const [archived, setArchived] = useState(car?.archived ?? false);
  const save = useGroupMutation<Record<string, unknown>>(car ? 'PUT' : 'POST', () => (car ? `/cars/${car.id}` : '/cars'), (v) => v);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(
      {
        name: name.trim(),
        plate: plate.trim() || null,
        start_odometer_km: parseKm(startKm) ?? 0,
        energy_unit: energy,
        ...(car ? { archived } : {}),
      },
      {
        onSuccess: () => {
          toast(t.common.saved);
          onDone();
        },
      },
    );
  };
  return (
    <form className="form mt-1" onSubmit={submit}>
      <div className="grid-2">
        <label className="field"><span>{c.name}</span><input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} /></label>
        <label className="field"><span>{c.plate}</span><input value={plate} onChange={(e) => setPlate(e.target.value)} maxLength={20} /></label>
      </div>
      <div className="grid-2">
        <label className="field">
          <span>{c.startKm}</span>
          <input inputMode="numeric" value={startKm} onChange={(e) => setStartKm(e.target.value)} required />
        </label>
        <label className="field">
          <span>{c.energy}</span>
          <select value={energy} onChange={(e) => setEnergy(e.target.value as EnergyUnit)}>
            <option value="l">{c.combustion}</option>
            <option value="kWh">{c.electric}</option>
          </select>
        </label>
      </div>
      {car && (
        <label className="check"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />{c.archived}</label>
      )}
      {save.isError && <p className="error" role="alert">{errorText(save.error)}</p>}
      <div className="button-row mt-0">
        <button type="submit" className="button primary" disabled={save.isPending}>{t.common.save}</button>
        <button type="button" className="button" onClick={onDone}>{t.common.cancel}</button>
      </div>
    </form>
  );
}

/** All IANA zones the browser knows; the current value is always offered. */
function useTimezones(current: string | null): string[] {
  return useMemo(() => {
    const supported = (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') ?? [];
    const zones = new Set(supported);
    if (current) zones.add(current);
    return [...zones].sort();
  }, [current]);
}

function GroupSettings({ group }: { group: Group }) {
  const t = useT();
  const g = t.group;
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [name, setName] = useState(group.name);
  const [currency, setCurrency] = useState(group.currency);
  const [timezone, setTimezone] = useState(group.timezone ?? '');
  const timezones = useTimezones(group.timezone);
  const currencies = COMMON_CURRENCIES.includes(group.currency) ? COMMON_CURRENCIES : [group.currency, ...COMMON_CURRENCIES];
  const save = useGroupMutation<Record<string, unknown>>('PATCH', () => '', (v) => v);
  const changed = name.trim() !== group.name || currency !== group.currency || (timezone || null) !== group.timezone;
  // The default label shows the server's zone only while the group uses it
  const serverZone = group.timezone ? null : group.effective_timezone;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body: Record<string, unknown> = { timezone: timezone || null };
    if (name.trim() !== group.name) body.name = name.trim();
    if (currency !== group.currency) body.currency = currency;
    save.mutate(body, {
      onSuccess: () => {
        toast(t.common.saved);
        void queryClient.invalidateQueries({ queryKey: ME_KEY });
      },
    });
  };
  return (
    <form className="card form" onSubmit={submit}>
      <h2 className="mt-0">{g.settings}</h2>
      <label className="field">
        <span>{g.rename}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
      </label>
      <div className="grid-2">
        <label className="field">
          <span>{g.currency}</span>
          <select value={currency} onChange={(e) => setCurrency(e.target.value)} aria-describedby="currency-hint">
            {currencies.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
          <span id="currency-hint" className="hint">{g.currencyLocked}</span>
        </label>
        <label className="field">
          <span>{g.timezone}</span>
          <select value={timezone} onChange={(e) => setTimezone(e.target.value)} aria-describedby="timezone-hint">
            <option value="">{g.timezoneDefault(serverZone ?? '…')}</option>
            {timezones.map((zone) => <option key={zone} value={zone}>{zone.replace(/_/g, ' ')}</option>)}
          </select>
          <span id="timezone-hint" className="hint">{g.timezoneHint}</span>
        </label>
      </div>
      {save.isError && <p className="error" role="alert">{errorText(save.error)}</p>}
      <button type="submit" className="button" disabled={save.isPending || !changed}>{t.common.save}</button>
    </form>
  );
}

function DataExport() {
  const t = useT();
  const { lang } = useI18n();
  const gid = useGroupId();
  return (
    <section>
      <h2>{t.group.data}</h2>
      <p className="button-row">
        <a className="button" href={apiUrl(`/v1/groups/${gid}/export.csv?lang=${lang}`)} download>{t.group.csv}</a>
        <a className="button" href={apiUrl(`/v1/groups/${gid}/export.json`)} download>{t.group.json}</a>
      </p>
      <p className="subtle small">{t.group.jsonHint}</p>
    </section>
  );
}

function AuditLog() {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <section>
      <h2>{t.group.audit}</h2>
      {!open && <button type="button" className="button small" onClick={() => setOpen(true)}>{t.group.showAudit}</button>}
      {open && <AuditList />}
    </section>
  );
}

function AuditList() {
  const t = useT();
  const g = t.group;
  const f = useFormat();
  const audit = useAudit();
  const name = useMemberNames();
  const state = queryState([audit], !!audit.data);
  if (state) return state;
  return (
    <ul className="list card">
      {audit.data!.map((a) => (
        <li key={a.id} className="row">
          <span className="main">
            <span className="title">{g.auditEntry(g.entities[a.entity] ?? a.entity, g.actions[a.action] ?? a.action)}</span>
            <div className="meta">{name(a.user_id)} · {f.date(a.created_at)}</div>
          </span>
        </li>
      ))}
    </ul>
  );
}

function DeleteGroup({ group }: { group: Group }) {
  const t = useT();
  const g = t.group;
  const { toast } = useFeedback();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  // Not useGroupMutation: refetching the deleted group would flash "not found"
  const remove = useMutation({
    mutationFn: () => apiFetch<void>(`/v1/groups/${group.id}`, { method: 'DELETE', body: JSON.stringify({ name }) }),
    onSuccess: async () => {
      toast(g.deleted);
      navigate('/', { replace: true });
      queryClient.removeQueries({ queryKey: ['group', group.id] });
      await queryClient.invalidateQueries({ queryKey: ME_KEY });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    remove.mutate();
  };
  return (
    <details className="card danger-zone">
      <summary><h2 className="inline">{g.deleteTitle}</h2></summary>
      <form className="form mt-1" onSubmit={submit}>
        <p className="m-0">{g.deleteIntro}</p>
        <label className="field">
          <span>{g.deleteConfirmName(group.name)}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required autoComplete="off" />
        </label>
        {remove.isError && <p className="error" role="alert">{errorText(remove.error)}</p>}
        <button type="submit" className="button primary danger" disabled={remove.isPending || name.trim() !== group.name.trim()}>
          {g.deleteSubmit}
        </button>
      </form>
    </details>
  );
}
