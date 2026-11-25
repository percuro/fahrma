import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { errorText } from '../lib/api';
import { parseKm } from '../lib/format';
import { energyKind } from '../lib/cars';
import type { Car, Trip } from '../lib/types';
import {
  isValidGroupId,
  useBalance,
  useCars,
  useGroup,
  useGroupId,
  useGroupMutation,
  useMemberNames,
  useOpenTransfers,
  useTrips,
} from '../hooks/useGroupData';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { BoltIcon, CarIcon, FuelIcon, ReceiptIcon } from '../components/Icons';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { GroupNotFound } from '../components/GroupNotFound';
import { writeLastGroup } from '../lib/storage';

const tone = (cents: number) => (cents < 0 ? 'minus' : cents > 0 ? 'plus' : '');

export function DashboardPage() {
  const t = useT();
  const d = t.dashboard;
  const f = useFormat();
  const gid = useGroupId();
  const me = useSession();
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
  const state = queryState([group, cars, balance], !!(group.data && cars.data && balance.data));
  if (state) return state;
  const groupData = group.data!;
  const carList = cars.data!;
  const balanceData = balance.data!;

  const mine = balanceData.members.find((m) => m.user_id === me.id);
  const myBalance = mine?.balance_cents ?? 0;
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

      {activeCars.length > 0 && (
        <div className="actions">
          <Link className="button primary" to={`/g/${gid}/trip/new`}><CarIcon />{d.trip}</Link>
          <Link className="button" to={`/g/${gid}/fuel/new`}>
            {kind === 'charge' ? <BoltIcon /> : <FuelIcon />}
            {kind === 'fuel' ? d.fuel : kind === 'charge' ? d.charge : d.fuelOrCharge}
          </Link>
          <Link className="button" to={`/g/${gid}/expense/new`}><ReceiptIcon />{d.expense}</Link>
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <div className="label">{d.yourBalance}</div>
          <div className={`value ${tone(myBalance)}`}>{f.money(myBalance)}</div>
          <div className="subtle small">{myBalance < 0 ? d.youPay : myBalance > 0 ? d.youGet : d.even}</div>
        </div>
        <div className="stat">
          <div className="label">{d.yourKm}</div>
          <div className="value">{f.km(mine?.km ?? 0)}</div>
          <div className="subtle small">{balanceData.period_start ? d.sinceDate(f.date(balanceData.period_start)) : d.sinceStart}</div>
        </div>
        {balanceData.cars.filter((c) => activeCars.some((a) => a.id === c.car_id)).map((c) => (
          <div className="stat" key={c.car_id}>
            <div className="label">{c.name}</div>
            <div className="value">{f.rate(c.rate_cents_per_km ?? c.last_rate_cents_per_km)}</div>
            <div className="subtle small">
              {c.rate_cents_per_km !== null ? d.rateEstimate : c.last_rate_cents_per_km !== null ? d.rateLast : d.rateNone}
            </div>
          </div>
        ))}
      </div>

      <section className="card">
        <h2 className="mt-0">{d.balanceTitle}</h2>
        <ul className="list">
          {balanceData.members.map((m) => (
            <li key={m.user_id} className="row">
              <span className="main">
                <span className="title">{m.display_name}</span>
                <div className="meta">{f.km(m.km)} · {d.paidAmount(f.money(m.paid_cents))}</div>
              </span>
              <span className={`num ${tone(m.balance_cents)}`}>{f.signedMoney(m.balance_cents)}</span>
            </li>
          ))}
        </ul>
        {balanceData.transfers.length > 0 && (
          <>
            <h3>{d.ifSettledNow}</h3>
            <ul className="list">
              {balanceData.transfers.map((tr) => (
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
        <Link to={`/g/${gid}/history`}>{d.allEntries}</Link>
      </section>
    </>
  );
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
  const [endKm, setEndKm] = useState('');
  const finish = useGroupMutation<number>('POST', () => `/trips/${trip.id}/finish`, (end_km) => ({ end_km }));
  const parsed = parseKm(endKm);
  const valid = parsed !== null && parsed >= trip.start_km;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) finish.mutate(parsed, { onSuccess: () => toast(d.tripFinished) });
  };
  const errorId = `finish-${trip.id}-error`;
  return (
    <form className="card form highlight" onSubmit={submit}>
      <div>{d.onTheRoad(car?.name ?? t.common.car, driver, f.date(trip.date), f.km(trip.start_km))}</div>
      <div className="grid-2">
        <label className="field">
          <span>{d.odometerNow}</span>
          <input inputMode="numeric" value={endKm} onChange={(e) => setEndKm(e.target.value)} required
            aria-invalid={finish.isError} aria-describedby={finish.isError ? errorId : undefined} />
        </label>
        <button type="submit" className="button primary align-end" disabled={finish.isPending || !valid}>
          {valid ? d.finishTripKm(f.km(parsed - trip.start_km)) : d.finishTrip}
        </button>
      </div>
      {finish.isError && <p id={errorId} className="error" role="alert">{errorText(finish.error)}</p>}
    </form>
  );
}
