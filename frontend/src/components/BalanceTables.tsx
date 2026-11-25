import type { Balance } from '../lib/types';
import { useT } from '../i18n';
import { useFormat } from '../hooks/useFormat';

const tone = (cents: number) => (cents < 0 ? 'minus' : cents > 0 ? 'plus' : '');

/** Tables for the preview and for a completed settlement (same layout). */
export function BalanceTables({ balance }: { balance: Balance }) {
  const t = useT();
  const b = t.balance;
  const f = useFormat();
  const hasExternal = balance.members.some((m) => m.external_credit_cents || m.external_held_cents);
  const hasExpenses = balance.members.some((m) => m.expense_cost_cents);
  return (
    <>
      <section className="card">
        <h2 className="mt-0">{b.cars}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th scope="col">{t.common.car}</th><th scope="col" className="num">km</th><th scope="col" className="num">{b.fuelCosts}</th><th scope="col" className="num">{b.rate}</th></tr>
            </thead>
            <tbody>
              {balance.cars.map((c) => (
                <tr key={c.car_id}>
                  <td>{c.name}{c.carried_fuel_cents > 0 && <div className="subtle small">{b.carried(f.money(c.carried_fuel_cents))}</div>}</td>
                  <td className="num">{f.km(c.km)}</td>
                  <td className="num">{f.money(c.fuel_cents)}</td>
                  <td className="num">{f.rate(c.rate_cents_per_km)}</td>
                </tr>
              ))}
              {balance.cars.length === 0 && <tr><td colSpan={4} className="subtle">{b.noTrips}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <h2 className="mt-0">{b.people}</h2>
        <ul className="list">
          {balance.members.map((m) => (
            <li key={m.user_id} className="row">
              <span className="main">
                <span className="title">{m.display_name}</span>
                <div className="meta wrap">
                  {[
                    f.km(m.km),
                    b.trips(f.money(m.trip_cost_cents)),
                    hasExpenses && b.expenses(f.money(m.expense_cost_cents)),
                    m.external_credit_cents > 0 && b.passengers(f.money(m.external_credit_cents)),
                    m.external_held_cents > 0 && b.cashReceived(f.money(m.external_held_cents)),
                    b.paid(f.money(m.paid_cents)),
                  ].filter(Boolean).join(' · ')}
                </div>
              </span>
              <strong className={`num ${tone(m.balance_cents)}`}>{f.signedMoney(m.balance_cents)}</strong>
            </li>
          ))}
        </ul>
        <p className="subtle small">
          {b.explanation}
          {hasExternal && ` ${b.externalExplanation}`}
        </p>
      </section>
    </>
  );
}
