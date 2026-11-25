import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { errorText, isNetworkError } from '../lib/api';
import { draftError, removeDraft, retryDraft, type Draft } from '../lib/outbox';
import { useDrafts, useEntrySave } from '../hooks/useDrafts';
import { parseKm } from '../lib/format';
import { energyKind } from '../lib/cars';
import type { Balance as BalanceData, Car, Group, Trip } from '../lib/types';
import { nowIn } from '../lib/dates';
import {
  isValidGroupId,
  useBalance,
  useCars,
  useGroup,
  useGroupId,
  useMemberNames,
  useOpenTransfers,
  useReservations,
  useTrips,
} from '../hooks/useGroupData';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { BoltIcon, CarIcon, FuelIcon, ReceiptIcon } from '../components/Icons';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { LoadError, Loading } from '../components/Status';
import { GroupNotFound } from '../components/GroupNotFound';
import { writeLastGroup } from '../lib/storage';

const tone = (cents: number) => (cents < 0 ? 'minus' : cents > 0 ? 'plus' : '');

export function DashboardPage() {
  const t = useT();
  const d = t.dashboard;
  const f = useFormat();
  const gid = useGroupId();
  const group = useGroup();
  const cars = useCars();
  const balance = useBalance();
  const trips = useTrips();
  const openTransfers = useOpenTransfers();
  const name = useMemberNames();

  useEffect(() => {
    if (group.data) writeLastGroup(gid);
  }, [gid, group.data]);

  if (!isValidGroupId(gid)) return <GroupNotFound />;
  // Group and cars may come from the offline cache; the balance is only ever shown fresh
  const state = queryState([group, cars], !!(group.data && cars.data));
  if (state) return state;
  const groupData = group.data!;
  const carList = cars.data!;
  const balanceData = balance.data;
  const openTrips = (trips.data ?? []).filter((trip) => trip.end_km === null);
  const activeCars = carList.filter((c) => !c.archived);
  const kind = energyKind(carList);

  return (
    <>
      <h1>{groupData.name}</h1>

      {activeCars.length === 0 && (
        <div className="notice">
          {d.noCar}{' '}
          {groupData.my_role === 'admin' ? <Link to={`/g/${gid}/group`}>{d.addCarNow}</Link> : d.askAdmin}
        </div>
      )}

      {openTrips.map((trip) => (
        <FinishTrip key={trip.id} trip={trip} car={carList.find((c) => c.id === trip.car_id)} driver={name(trip.shares[0]?.user_id)} />
      ))}

      <Drafts trips={trips.data ?? []} />

      {activeCars.length > 0 && (
        <div className="quick-actions">
          <Link className="button primary" to={`/g/${gid}/trip/new`}><CarIcon />{d.trip}</Link>
          <Link className="button" to={`/g/${gid}/fuel/new`}>
            {kind === 'charge' ? <BoltIcon /> : <FuelIcon />}
            {kind === 'fuel' ? d.fuel : kind === 'charge' ? d.charge : d.fuelOrCharge}
          </Link>
          <Link className="button" to={`/g/${gid}/expense/new`}><ReceiptIcon />{d.expense}</Link>
        </div>
      )}

      {balanceData ? (
        <Balance balance={balanceData} activeCars={activeCars} />
      ) : balance.isError && isNetworkError(balance.error) ? (
        <p className="notice">{t.offline.balanceOffline}</p>
      ) : balance.isError ? (
        <LoadError error={balance.error} onRetry={() => void balance.refetch()} />
      ) : (
        <Loading />
      )}

      {(openTransfers.data?.length ?? 0) > 0 && (
        <section className="card">
          <h2 className="mt-0">{d.openTransfers}</h2>
          <ul className="list">
            {openTransfers.data!.map((tr) => (
              <li key={tr.id} className="row">
                <Link className="main" to={`/g/${gid}/settlement/${tr.settlement_id}`}>
                  {name(tr.from_user_id)} → {name(tr.to_user_id)}
                </Link>
                <span className="num">{f.money(tr.amount_cents)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {activeCars.length > 0 && <Reservations group={groupData} cars={activeCars} />}

      <section>
        <h2>{d.recentTrips}</h2>
        {trips.isError ? (
          queryState([trips], false)
        ) : (
          <ul className="list card">
            {(trips.data ?? []).slice(0, 5).map((trip) => (
              <li key={trip.id}><TripRow trip={trip} /></li>
            ))}
            {trips.data?.length === 0 && <li className="subtle">{d.noTrips}</li>}
          </ul>
        )}
        <p className="link-row">
          <Link to={`/g/${gid}/history`}>{d.allEntries}</Link>
          {carList.length > 0 && <Link to={`/g/${gid}/stats`}>{t.stats.link}</Link>}
        </p>
      </section>
    </>
  );
}

/** What is reserved now and next; a reservation that is over is not shown. */
function Reservations({ group, cars }: { group: Group; cars: Car[] }) {
  const t = useT();
  const r = t.reservation;
  const f = useFormat();
  const gid = useGroupId();
  const name = useMemberNames();
  const reservations = useReservations();
  const now = nowIn(group.effective_timezone);
  const upcoming = (reservations.data ?? []).filter((x) => x.ends_at.slice(0, 16) > now).slice(0, 3);
  const carName = (id: number) => cars.find((c) => c.id === id)?.name;
  return (
    <section>
      <h2>{r.upcoming}</h2>
      {reservations.isError ? (
        <p className="subtle">{errorText(reservations.error)}</p>
      ) : reservations.data ? (
        <ul className="list card">
          {upcoming.map((x) => (
            <li key={x.id}>
              <Link className="row" to={`/g/${gid}/reservation/${x.id}`}>
                <span className="main">
                  <span className="title">{name(x.user_id)}</span>
                  <div className="meta">
                    {[f.span(x.starts_at, x.ends_at), cars.length > 1 ? carName(x.car_id) : null].filter(Boolean).join(' · ')}
                  </div>
                </span>
                {x.starts_at.slice(0, 16) <= now && <span className="badge accent">{r.now}</span>}
              </Link>
            </li>
          ))}
          {upcoming.length === 0 && <li className="row subtle">{r.noneUpcoming}</li>}
        </ul>
      ) : (
        <Loading />
      )}
      <p className="link-row">
        <Link to={`/g/${gid}/calendar`}>{r.toCalendar}</Link>
        <Link to={`/g/${gid}/reservation/new`}>{r.reserve}</Link>
      </p>
    </section>
  );
}

function Balance({ balance, activeCars }: { balance: BalanceData; activeCars: Car[] }) {
  const t = useT();
  const d = t.dashboard;
  const f = useFormat();
  const gid = useGroupId();
  const me = useSession();
  const name = useMemberNames();
  const mine = balance.members.find((m) => m.user_id === me.id);
  const myBalance = mine?.balance_cents ?? 0;
  return (
    <>
      <div className="stats">
        <div className="stat hero">
          <div className="label">{d.yourBalance}</div>
          <div className={`value ${tone(myBalance)}`}>{f.money(myBalance)}</div>
          <div className="subtle small">{myBalance < 0 ? d.youPay : myBalance > 0 ? d.youGet : d.even}</div>
        </div>
        <div className="stat">
          <div className="label">{d.yourKm}</div>
          <div className="value">{f.km(mine?.km ?? 0)}</div>
          <div className="subtle small">{balance.period_start ? d.sinceDate(f.date(balance.period_start)) : d.sinceStart}</div>
        </div>
        {balance.cars.filter((c) => activeCars.some((a) => a.id === c.car_id)).map((c) => (
          <Link className="stat" key={c.car_id} to={`/g/${gid}/stats?car=${c.car_id}`}>
            {/* The name of the link contains what is visible, and says where it leads */}
            <span className="sr-only">{d.carStats(c.name)}: </span>
            <div className="label">{c.name}</div>
            <div className="value">{f.rate(c.rate_cents_per_km ?? c.last_rate_cents_per_km)}</div>
            <div className="subtle small">
              {c.rate_cents_per_km !== null ? d.rateEstimate : c.last_rate_cents_per_km !== null ? d.rateLast : d.rateNone}
            </div>
          </Link>
        ))}
      </div>

      <section className="card">
        <h2 className="mt-0">{d.balanceTitle}</h2>
        <ul className="list">
          {balance.members.map((m) => (
            <li key={m.user_id} className="row">
              <span className="main">
                <span className="title">{m.display_name}</span>
                <div className="meta">{f.km(m.km)} · {d.paidAmount(f.money(m.paid_cents))}</div>
              </span>
              <span className={`num ${tone(m.balance_cents)}`}>{f.signedMoney(m.balance_cents)}</span>
            </li>
          ))}
        </ul>
        {balance.transfers.length > 0 && (
          <>
            <h3>{d.ifSettledNow}</h3>
            <ul className="list">
              {balance.transfers.map((tr) => (
                <li key={`${tr.from_user_id}-${tr.to_user_id}`} className="row">
                  <span className="main">{name(tr.from_user_id)} → {name(tr.to_user_id)}</span>
                  <span className="num">{f.money(tr.amount_cents)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="button-row">
          <Link className="button small" to={`/g/${gid}/settlement`}>{d.toSettlement}</Link>
        </div>
      </section>
    </>
  );
}

/** Entries saved on this device that have not reached the server yet. */
function Drafts({ trips }: { trips: Trip[] }) {
  const t = useT();
  const o = t.offline;
  const f = useFormat();
  const gid = useGroupId();
  const cars = useCars();
  const drafts = useDrafts(gid);
  if (drafts.length === 0) return null;
  const carName = (id: number | null | undefined) => cars.data?.find((c) => c.id === id)?.name ?? t.common.car;

  const describe = (draft: Draft): { title: string; meta: string; to: string | null } => {
    const open = (kind: string) => `/g/${gid}/${kind}/new?draft=${draft.id}`;
    switch (draft.kind) {
      case 'trip': {
        const body = (draft as Draft<'trip'>).body;
        const km = body.end_km === null ? t.trip.running(f.km(body.start_km)) : f.km(body.end_km - body.start_km);
        return { title: draft.entityId ? o.tripChange : o.trip, meta: [f.date(body.date), carName(body.car_id), km].join(' · '), to: open('trip') };
      }
      case 'fuel': {
        const body = (draft as Draft<'fuel'>).body;
        return { title: draft.entityId ? o.fuelChange : o.fuel, meta: [f.date(body.date), carName(body.car_id), f.money(body.amount_cents)].join(' · '), to: open('fuel') };
      }
      case 'expense': {
        const body = (draft as Draft<'expense'>).body;
        return { title: draft.entityId ? o.expenseChange : o.expense, meta: [f.date(body.date), t.expense.categories[body.category], f.money(body.amount_cents)].join(' · '), to: open('expense') };
      }
      case 'finish': {
        const trip = trips.find((x) => x.id === draft.entityId);
        const end = (draft as Draft<'finish'>).body.end_km;
        return { title: o.finish, meta: [trip && carName(trip.car_id), o.finishAt(f.km(end))].filter(Boolean).join(' · '), to: null };
      }
    }
  };

  return (
    <section className="card highlight" aria-labelledby="drafts-title">
      <h2 id="drafts-title" className="mt-0">{o.draftsTitle(drafts.length)}</h2>
      <p className="subtle small m-0">{o.draftsHint}</p>
      <ul className="list">
        {drafts.map((draft) => {
          const { title, meta, to } = describe(draft);
          const error = draftError(draft);
          const content = (
            <span className="main">
              <span className="title">{title}</span>
              <div className="meta">{meta}</div>
              {error && <div className="error small">{o.refused(errorText(error))}</div>}
            </span>
          );
          return (
            <li key={draft.id} className="draft-row">
              {to ? <Link className="row" to={to}>{content}</Link> : <div className="row">{content}</div>}
              <span className="badge">{error ? o.stateRefused : o.stateWaiting}</span>
              {error && draft.kind === 'finish' && (
                <span className="button-row">
                  <button type="button" className="button small" onClick={() => retryDraft(draft.id)}>{o.retry}</button>
                  <DiscardDraft draft={draft} />
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DiscardDraft({ draft }: { draft: Draft }) {
  const t = useT();
  const { toast, confirm } = useFeedback();
  const discard = async () => {
    if (!(await confirm(t.offline.confirmDiscard, { confirmLabel: t.offline.discard, danger: true }))) return;
    removeDraft(draft.id);
    toast(t.offline.discarded);
  };
  return <button type="button" className="button small danger" onClick={discard}>{t.offline.discard}</button>;
}

export function TripRow({ trip }: { trip: Trip }) {
  const t = useT();
  const f = useFormat();
  const gid = useGroupId();
  const name = useMemberNames();
  const cars = useCars();
  const carName = cars.data && cars.data.length > 1 ? cars.data.find((c) => c.id === trip.car_id)?.name : null;
  const passengers = trip.external.reduce((sum, e) => sum + e.amount_cents, 0);
  const meta = [
    f.date(trip.date),
    carName,
    trip.end_km === null ? t.trip.running(f.km(trip.start_km)) : f.km(trip.km),
    trip.external.length > 0 && t.trip.passengers(f.money(passengers)),
    trip.note,
  ].filter(Boolean);
  return (
    <Link className="row" to={`/g/${gid}/trip/${trip.id}`}>
      <span className="main">
        <span className="title">{trip.shares.map((s) => name(s.user_id)).join(' + ')}</span>
        <div className="meta">{meta.join(' · ')}</div>
      </span>
      <span className="num">
        {trip.cost_cents !== null ? `${trip.cost_is_estimate ? '≈ ' : ''}${f.money(trip.cost_cents)}` : ''}
      </span>
      {trip.settlement_id !== null && <span className="badge">{t.common.settled}</span>}
    </Link>
  );
}

function FinishTrip({ trip, car, driver }: { trip: Trip; car?: Car; driver: string }) {
  const t = useT();
  const d = t.dashboard;
  const f = useFormat();
  const { toast } = useFeedback();
  const gid = useGroupId();
  const pending = useDrafts(gid).find((draft) => draft.kind === 'finish' && draft.entityId === trip.id);
  const [endKm, setEndKm] = useState('');
  const finish = useEntrySave('finish', trip.id);
  const parsed = parseKm(endKm);
  const valid = parsed !== null && parsed >= trip.start_km;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) {
      finish.mutate({ end_km: parsed }, {
        onSuccess: (outcome) => toast(outcome === 'draft' ? t.offline.savedAsDraft : d.tripFinished),
      });
    }
  };
  // Finished on this device, not sent yet: listed with the drafts
  if (pending) return null;
  const errorId = `finish-${trip.id}-error`;
  return (
    <form className="card feature form" onSubmit={submit}>
      <div className="running-head">
        <span className="badge accent">{d.running}</span>
        <strong>{d.carOnTheRoad(car?.name ?? t.common.car)}</strong>
      </div>
      <div>
        <div className="figure">{f.km(trip.start_km)}</div>
        <div className="subtle small">{d.startedBy(driver, f.date(trip.date))}</div>
      </div>
      <div className="finish-row">
        <label className="field">
          <span>{d.odometerNow}</span>
          <input inputMode="numeric" value={endKm} onChange={(e) => setEndKm(e.target.value)} required
            aria-invalid={finish.isError} aria-describedby={finish.isError ? errorId : undefined} />
        </label>
        <button type="submit" className="button primary" disabled={finish.isPending || !valid}>
          {valid ? d.finishTripKm(f.km(parsed - trip.start_km)) : d.finishTrip}
        </button>
      </div>
      {finish.isError && <p id={errorId} className="error" role="alert">{errorText(finish.error)}</p>}
    </form>
  );
}
