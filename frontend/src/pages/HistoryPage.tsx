import { Link } from 'react-router-dom';
import { useCars, useExpenses, useFuel, useGroupId, useMemberNames, useTrips } from '../hooks/useGroupData';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { queryState } from '../components/queryState';
import { TripRow } from './DashboardPage';
import { ReceiptIcon } from '../components/Icons';
import { Tabs } from '../components/Tabs';

const TABS = ['trips', 'fuel', 'expenses'] as const;

export function HistoryPage() {
  const t = useT();
  const labels = { trips: t.history.trips, fuel: t.history.fuel, expenses: t.history.expenses };
  return (
    <>
      <h1>{t.history.title}</h1>
      <Tabs id="history" tabs={TABS} labels={labels} label={t.history.tabs}>
        {(tab) => (
          <>
            {tab === 'trips' && <TripList />}
            {tab === 'fuel' && <FuelList />}
            {tab === 'expenses' && <ExpenseList />}
          </>
        )}
      </Tabs>
    </>
  );
}

function TripList() {
  const t = useT();
  const trips = useTrips();
  const state = queryState([trips], !!trips.data);
  if (state) return state;
  if (trips.data!.length === 0) return <p className="subtle">{t.dashboard.noTrips}</p>;
  return (
    <ul className="list card">
      {trips.data!.map((trip) => <li key={trip.id}><TripRow trip={trip} /></li>)}
    </ul>
  );
}

/** A small receipt symbol on entries with photos; the word is there for screen readers. */
function HasReceipt({ count }: { count: number }) {
  const t = useT();
  if (count === 0) return null;
  return (
    <span className="receipt-mark" title={t.receipts.listed}>
      <ReceiptIcon />
      <span className="sr-only">{t.receipts.listed}</span>
    </span>
  );
}

function FuelList() {
  const t = useT();
  const f = useFormat();
  const gid = useGroupId();
  const fuel = useFuel();
  const cars = useCars();
  const name = useMemberNames();
  const state = queryState([fuel, cars], !!(fuel.data && cars.data));
  if (state) return state;
  if (fuel.data!.length === 0) return <p className="subtle">{t.fuel.noEntries}</p>;
  const multiCar = cars.data!.length > 1;
  return (
    <ul className="list card">
      {fuel.data!.map((entry) => {
        const car = cars.data!.find((c) => c.id === entry.car_id);
        const meta = [
          f.date(entry.date),
          multiCar && car?.name,
          entry.quantity_milli && f.quantity(entry.quantity_milli, car?.energy_unit ?? 'l'),
          entry.odometer_km && t.fuel.atKm(f.km(entry.odometer_km)),
        ].filter(Boolean);
        return (
          <li key={entry.id}>
            <Link className="row" to={`/g/${gid}/fuel/${entry.id}`}>
              <span className="main">
                <span className="title">{name(entry.paid_by_user_id)}</span>
                <div className="meta">{meta.join(' · ')}</div>
              </span>
              <span className="num">{f.money(entry.amount_cents)}</span>
              <HasReceipt count={entry.receipts?.length ?? 0} />
              {entry.settlement_id !== null && <span className="badge">{t.common.settled}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function ExpenseList() {
  const t = useT();
  const x = t.expense;
  const f = useFormat();
  const gid = useGroupId();
  const expenses = useExpenses();
  const name = useMemberNames();
  const state = queryState([expenses], !!expenses.data);
  if (state) return state;
  if (expenses.data!.length === 0) return <p className="subtle">{x.noEntries}</p>;
  return (
    <ul className="list card">
      {expenses.data!.map((e) => (
        <li key={e.id}>
          <Link className="row" to={`/g/${gid}/expense/${e.id}`}>
            <span className="main">
              <span className="title">{x.categories[e.category] ?? e.category}{e.description ? ` · ${e.description}` : ''}</span>
              <div className="meta">
                {[
                  f.date(e.date),
                  x.paidByName(name(e.paid_by_user_id)),
                  e.allocation === 'single' ? x.onlyName(name(e.allocated_user_id)) : x.allocations[e.allocation].label,
                ].join(' · ')}
              </div>
            </span>
            <span className="num">{f.money(e.amount_cents)}</span>
            <HasReceipt count={e.receipts?.length ?? 0} />
            {e.settlement_id !== null && <span className="badge">{t.common.settled}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}
