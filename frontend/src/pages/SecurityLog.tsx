import { useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import type {
  AdminUser,
  OwnSecurityEvent,
  OwnSecurityEventPage,
  SecurityDetails,
  SecurityEvent,
  SecurityEventPage,
} from '../lib/types';
import { useFormat } from '../hooks/useFormat';
import { useOidcLabel } from '../hooks/useOidcLabel';
import { queryState } from '../components/queryState';
import { useI18n, useT } from '../i18n';
import { useMeta } from '../hooks/useMeta';
import { planName } from '../lib/plans';

const PAGE_SIZE = 50;
const OWN_PAGE_SIZE = 10;
const FAILURES = new Set(['auth.login_failed', 'auth.confirm_failed', 'auth.oidc_failed', 'auth.rate_limited', 'setup.failed']);

type SecurityTexts = ReturnType<typeof useT>['security'];

function title(s: SecurityTexts, event: string, details: SecurityDetails, provider: string): string {
  const text = s.events[event];
  return text ? text(details, provider) : event;
}

/** The parts after the title that do not depend on who looks: how, which limiter, from where. */
function extras(s: SecurityTexts, event: { ip_prefix: string | null; details: SecurityDetails }): string[] {
  const d = event.details;
  const parts: string[] = [];
  if (typeof d.via === 'string' && d.via !== 'cli') parts.push(s.via[d.via] ?? d.via);
  if (d.via === 'cli') parts.push(s.commandLine);
  if (d.by === 'operator') parts.push(s.operator);
  if (d.by === 'inactive') parts.push(s.automatic);
  if (typeof d.limiter === 'string') parts.push(s.limiters[d.limiter] ?? d.limiter);
  if (event.ip_prefix) parts.push(s.from(event.ip_prefix));
  return parts;
}

/** Instance administration: every entry, filterable by account and by failures. */
export function AdminSecurityLog() {
  const t = useT();
  const s = t.security;
  const f = useFormat();
  const provider = useOidcLabel();
  const { lang } = useI18n();
  const plans = useMeta().data?.plans ?? null;
  // plan.changed stores the plan's id; show its name like the group list does
  const withNames = (event: SecurityEvent): SecurityDetails => {
    const plan = event.details.plan;
    if (event.event !== 'plan.changed' || typeof plan !== 'string') return event.details;
    return { ...event.details, plan: planName(plans?.find((p) => p.id === plan)?.name, lang) || plan };
  };
  const [userId, setUserId] = useState('');
  const [failures, setFailures] = useState(false);
  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: () => apiFetch<AdminUser[]>('/v1/admin/users') });
  const log = useInfiniteQuery({
    queryKey: ['admin', 'security-log', userId, failures],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (pageParam) params.set('before_id', String(pageParam));
      if (userId) params.set('user_id', userId);
      if (failures) params.set('failures', 'true');
      return apiFetch<SecurityEventPage>(`/v1/admin/security-log?${params}`);
    },
    getNextPageParam: (page) => page.next_before_id,
  });
  const state = queryState([log], !!log.data);
  const events = log.data?.pages.flatMap((page) => page.events) ?? [];
  const days = log.data?.pages[0]?.retention_days;

  const who = (event: SecurityEvent): string | null => {
    const actor = event.actor_username;
    const target = event.target_username;
    if (actor && target && event.actor_user_id !== event.target_user_id) return `@${actor} → @${target}`;
    if (target) return `@${target}`;
    if (actor) return `@${actor}`;
    return null;
  };

  return (
    <section className="card">
      <h2 className="mt-0">{s.title}</h2>
      {days !== undefined && <p className="subtle">{s.intro(days)}</p>}
      <div className="form">
        <label>
          {s.filterAccount}
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">{s.allAccounts}</option>
            {users.data?.map((u) => (
              <option key={u.id} value={u.id}>@{u.username}</option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={failures} onChange={(e) => setFailures(e.target.checked)} />
          {s.onlyFailures}
        </label>
      </div>
      {state ?? (events.length === 0 ? (
        <p className="subtle">{s.empty}</p>
      ) : (
        <ul className="list security-log">
          {events.map((event) => (
            <li key={event.id} className={FAILURES.has(event.event) ? 'row warn' : 'row'}>
              <span className="main">
                <span className="title">{title(s, event.event, withNames(event), provider)}</span>
                <div className="meta">
                  {[f.moment(event.created_at), who(event), ...extras(s, event)].filter(Boolean).join(' · ')}
                </div>
              </span>
            </li>
          ))}
        </ul>
      ))}
      {log.hasNextPage && (
        <button type="button" className="button small mt-1" onClick={() => log.fetchNextPage()} disabled={log.isFetchingNextPage}>
          {s.more}
        </button>
      )}
    </section>
  );
}

/** Profile: the entries about the own account. */
export function OwnSecurityLog() {
  const t = useT();
  const s = t.security;
  const f = useFormat();
  const provider = useOidcLabel();
  const log = useInfiniteQuery({
    queryKey: ['security-log'],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(OWN_PAGE_SIZE) });
      if (pageParam) params.set('before_id', String(pageParam));
      return apiFetch<OwnSecurityEventPage>(`/v1/account/security-log?${params}`);
    },
    getNextPageParam: (page) => page.next_before_id,
  });
  const state = queryState([log], !!log.data);
  const events = log.data?.pages.flatMap((page) => page.events) ?? [];
  const who = (event: OwnSecurityEvent) => (event.actor === 'admin' ? s.byAdmin : null);
  return (
    <section className="card">
      <h2 className="mt-0">{s.ownTitle}</h2>
      <p className="subtle">{s.ownIntro}</p>
      {state ?? (
        <ul className="list security-log">
          {events.map((event) => (
            <li key={event.id} className={FAILURES.has(event.event) ? 'row warn' : 'row'}>
              <span className="main">
                <span className="title">{title(s, event.event, event.details, provider)}</span>
                <div className="meta">
                  {[f.moment(event.created_at), who(event), ...extras(s, event)].filter(Boolean).join(' · ')}
                </div>
              </span>
            </li>
          ))}
        </ul>
      )}
      {log.hasNextPage && (
        <button type="button" className="button small mt-1" onClick={() => log.fetchNextPage()} disabled={log.isFetchingNextPage}>
          {s.more}
        </button>
      )}
    </section>
  );
}
