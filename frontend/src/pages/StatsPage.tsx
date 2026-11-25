import { useSearchParams } from 'react-router-dom';
import type { Car, CarStats, Group } from '../lib/types';
import { todayIn } from '../lib/dates';
import { useCars, useCarStats, useGroup, useMemberNames } from '../hooks/useGroupData';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { queryState } from '../components/queryState';
import { ColumnChart } from '../components/ColumnChart';

export function StatsPage() {
  const group = useGroup();
  const cars = useCars();
  const state = queryState([group, cars], !!(group.data && cars.data));
  if (state) return state;
  return <Stats group={group.data!} cars={cars.data!} />;
}

function Stats({ group, cars }: { group: Group; cars: Car[] }) {
  const t = useT();
  const st = t.stats;
  const [params, setParams] = useSearchParams();
  const requestedCar = Number(params.get('car'));
  const car = cars.find((c) => c.id === requestedCar) ?? cars.find((c) => !c.archived) ?? cars[0];
  const thisYear = Number(todayIn(group.effective_timezone, group.today).slice(0, 4));
  const yearParam = params.get('year');
  const year = yearParam === 'all' ? null : yearParam ? Number(yearParam) : thisYear;
  const stats = useCarStats(car?.id ?? null, year);

  const choose = (next: { car?: number; year?: number | null }) => {
    const carId = next.car ?? car?.id;
    const y = next.year === undefined ? year : next.year;
    setParams({ ...(carId ? { car: String(carId) } : {}), year: y === null ? 'all' : String(y) }, { replace: true });
  };

  if (!car) {
    return (
      <>
        <h1>{st.title}</h1>
        <p className="subtle">{st.noCar}</p>
      </>
    );
  }

  // The years with entries, plus the chosen one (so the selection never jumps)
  const years = [...new Set([...(stats.data?.years ?? []), thisYear, ...(year ? [year] : [])])].sort((a, b) => b - a);

  return (
    <>
      <h1>{st.title}</h1>
      <div className="filters">
        {cars.length > 1 && (
          <label className="field">
            <span>{t.common.car}</span>
            <select value={car.id} onChange={(e) => choose({ car: Number(e.target.value) })}>
              {cars.map((c) => (
                <option key={c.id} value={c.id}>{c.name}{c.archived ? ` (${st.archived})` : ''}</option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          <span>{st.period}</span>
          <select value={year ?? 'all'} onChange={(e) => choose({ year: e.target.value === 'all' ? null : Number(e.target.value) })}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
            <option value="all">{st.allYears}</option>
          </select>
        </label>
      </div>
      {queryState([stats], !!stats.data) ?? <StatsView stats={stats.data!} car={car} />}
    </>
  );
}

function StatsView({ stats, car }: { stats: CarStats; car: Car }) {
  const t = useT();
  const st = t.stats;
  const f = useFormat();
  const name = useMemberNames();
  const unit = stats.energy_unit;
  const electric = unit === 'kWh';
  const costs = stats.fuel_cents + stats.expense_cents;
  const c = stats.consumption;

  if (stats.km === 0 && stats.fuel_entries === 0 && stats.expense_cents === 0) {
    return <p className="subtle">{stats.year ? st.emptyYear(car.name, String(stats.year)) : st.empty(car.name)}</p>;
  }

  const columns = stats.periods.map((p) => ({
    key: p.period,
    label: f.period(p.period),
    narrow: f.period(p.period, true),
    value: p.km,
    detail: f.km(p.km),
  }));

  return (
    <>
      <div className="stats">
        <div className="stat">
          <div className="label">{st.driven}</div>
          <div className="value">{f.km(stats.km)}</div>
          <div className="subtle small">{st.trips(stats.trips)}</div>
        </div>
        <div className="stat">
          <div className="label">{electric ? st.consumptionElectric : st.consumption}</div>
          <div className="value">{c ? f.per100km(c.milli, c.km, unit) : '–'}</div>
          <div className="subtle small">{c ? st.consumptionBasis(f.km(c.km)) : st.consumptionMissing}</div>
        </div>
        <div className="stat">
          <div className="label">{st.costPer100}</div>
          <div className="value">{stats.km > 0 ? f.money(Math.round((costs * 100) / stats.km)) : '–'}</div>
          <div className="subtle small">{st.costTotal(f.money(costs))}</div>
        </div>
        <div className="stat">
          <div className="label">{electric ? st.pricePerKwh : st.pricePerLitre}</div>
          <div className="value">{stats.priced_milli > 0 ? f.unitPrice(stats.priced_cents, stats.priced_milli, unit) : '–'}</div>
          <div className="subtle small">{stats.priced_milli > 0 ? f.quantity(stats.priced_milli, unit) : st.noQuantities}</div>
        </div>
      </div>

      <section className="card">
        <h2 className="mt-0">{stats.year ? st.kmPerMonth : st.kmPerYear}</h2>
        <ColumnChart columns={columns} tick={(v) => f.km(v)}
          label={stats.year ? st.chartLabelMonths(car.name, String(stats.year)) : st.chartLabelYears(car.name)} />
        <div className="table-wrap">
          <table>
            <caption className="sr-only">{stats.year ? st.kmPerMonth : st.kmPerYear}</caption>
            <thead>
              <tr>
                <th scope="col">{stats.year ? st.month : st.year}</th>
                <th scope="col" className="num">km</th>
                <th scope="col" className="num">{electric ? st.charging : st.fuel}</th>
                <th scope="col" className="num">{st.otherShort}</th>
              </tr>
            </thead>
            <tbody>
              {stats.periods.map((p) => (
                <tr key={p.period}>
                  <th scope="row">{f.period(p.period)}</th>
                  <td className="num">{p.km ? f.km(p.km) : '–'}</td>
                  <td className="num">{p.fuel_cents ? f.money(p.fuel_cents) : '–'}</td>
                  <td className="num">{p.expense_cents ? f.money(p.expense_cents) : '–'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">{t.common.total}</th>
                <td className="num">{f.km(stats.km)}</td>
                <td className="num">{f.money(stats.fuel_cents)}</td>
                <td className="num">{f.money(stats.expense_cents)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <div className="split">
        <section className="card">
          <h2 className="mt-0">{st.costsTitle}</h2>
          <ul className="list">
            <li className="row">
              <span className="main">{electric ? st.charging : st.fuel}</span>
              <span className="num">{f.money(stats.fuel_cents)}</span>
            </li>
            {stats.categories.map((cat) => (
              <li key={cat.category} className="row">
                <span className="main">{t.expense.categories[cat.category] ?? cat.category}</span>
                <span className="num">{f.money(cat.cents)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2 className="mt-0">{st.whoDrove}</h2>
          {stats.members.length === 0 ? (
            <p className="subtle m-0">{st.noTrips}</p>
          ) : (
            <ul className="list">
              {stats.members.map((m) => (
                <li key={m.user_id} className="row">
                  <span className="main">{name(m.user_id)}</span>
                  <span className="num">{f.km(m.km)}</span>
                  <span className="subtle small share">{Math.round((m.km / stats.km) * 100)} %</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="subtle small">{st.note}</p>
    </>
  );
}
