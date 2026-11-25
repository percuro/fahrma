import { Link, useSearchParams } from 'react-router-dom';
import type { Car, Group, Reservation } from '../lib/types';
import { addDays, coversDay, nowIn, todayIn, weekStart } from '../lib/dates';
import { useCars, useGroup, useGroupId, useMemberNames, useReservations } from '../hooks/useGroupData';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { queryState } from '../components/queryState';
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon } from '../components/Icons';

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function CalendarPage() {
  const group = useGroup();
  const cars = useCars();
  const state = queryState([group, cars], !!(group.data && cars.data));
  if (state) return state;
  return <Calendar group={group.data!} cars={cars.data!} />;
}

function Calendar({ group, cars }: { group: Group; cars: Car[] }) {
  const t = useT();
  const r = t.reservation;
  const f = useFormat();
  const gid = useGroupId();
  const [params, setParams] = useSearchParams();
  const today = todayIn(group.effective_timezone, group.today);
  const requestedWeek = params.get('week');
  const week = weekStart(requestedWeek && DAY.test(requestedWeek) ? requestedWeek : today);
  const last = addDays(week, 6);
  const activeCars = cars.filter((c) => !c.archived);
  const car = activeCars.find((c) => c.id === Number(params.get('car'))) ?? null;
  const reservations = useReservations({ from: week, to: last }, car?.id);

  const choose = (next: { week?: string; car?: number | null }) => {
    const carId = next.car === undefined ? car?.id : next.car;
    setParams({ week: weekStart(next.week ?? week), ...(carId ? { car: String(carId) } : {}) }, { replace: true });
  };

  if (activeCars.length === 0) {
    return (
      <>
        <h1>{r.calendar}</h1>
        <p className="subtle">{r.noCar}</p>
      </>
    );
  }

  const newLink = `/g/${gid}/reservation/new${car ? `?car=${car.id}` : ''}`;
  return (
    <>
      <h1>{r.calendar}</h1>
      <div className="button-row mt-0 mb-075">
        <Link className="button primary" to={newLink}><CalendarIcon />{r.reserve}</Link>
      </div>
      {activeCars.length > 1 && (
        <div className="filters">
          <label className="field">
            <span>{t.common.car}</span>
            <select value={car?.id ?? ''} onChange={(e) => choose({ car: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{r.allCars}</option>
              {activeCars.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        </div>
      )}
      <div className="week-nav">
        <button type="button" className="button icon" onClick={() => choose({ week: addDays(week, -7) })} aria-label={r.previousWeek}><ChevronLeftIcon /></button>
        <strong aria-live="polite">{r.weekOf(f.weekday(week), f.weekday(last))}</strong>
        <button type="button" className="button icon" onClick={() => choose({ week: addDays(week, 7) })} aria-label={r.nextWeek}><ChevronRightIcon /></button>
        {week !== weekStart(today) && (
          <button type="button" className="button small" onClick={() => choose({ week: today })}>{r.thisWeek}</button>
        )}
      </div>
      {queryState([reservations], !!reservations.data) ?? (
        <Week week={week} today={today} group={group} cars={cars} carId={car?.id ?? null} showCar={!car && activeCars.length > 1}
          reservations={reservations.data!} />
      )}
    </>
  );
}

function Week({ week, today, group, cars, carId, showCar, reservations }: {
  week: string; today: string; group: Group; cars: Car[]; carId: number | null; showCar: boolean; reservations: Reservation[];
}) {
  const t = useT();
  const r = t.reservation;
  const f = useFormat();
  const gid = useGroupId();
  const name = useMemberNames();
  const now = nowIn(group.effective_timezone);
  const carName = (id: number) => cars.find((c) => c.id === id)?.name ?? '?';
  const days = Array.from({ length: 7 }, (_, i) => addDays(week, i));

  return (
    <>
      {days.map((day) => {
        const onDay = reservations.filter((x) => coversDay(x.starts_at, x.ends_at, day));
        return (
          <section key={day} className="day" aria-label={f.weekday(day)}>
            <h2 className="day-title">
              {f.weekday(day)}
              {day === today && <span className="badge accent">{r.today}</span>}
            </h2>
            <ul className="list card">
              {onDay.map((x) => {
                const sameDay = x.starts_at.slice(0, 10) === x.ends_at.slice(0, 10);
                const when = sameDay ? `${f.time(x.starts_at)}–${f.time(x.ends_at)}` : f.span(x.starts_at, x.ends_at);
                const active = x.starts_at.slice(0, 16) <= now && now < x.ends_at.slice(0, 16);
                return (
                  <li key={x.id}>
                    <Link className="row" to={`/g/${gid}/reservation/${x.id}`}>
                      <span className="main">
                        <span className="title">{name(x.user_id)}</span>
                        <div className="meta">{[when, showCar ? carName(x.car_id) : null, x.note].filter(Boolean).join(' · ')}</div>
                      </span>
                      {active && <span className="badge accent">{r.now}</span>}
                    </Link>
                  </li>
                );
              })}
              {onDay.length === 0 && (
                <li className="row subtle">
                  <Link className="main" to={`/g/${gid}/reservation/new?date=${day}${carId ? `&car=${carId}` : ''}`}>{r.free}</Link>
                </li>
              )}
            </ul>
          </section>
        );
      })}
    </>
  );
}
