import { useState, type FormEvent } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiError, errorText } from '../lib/api';
import { isErrorDetail } from '../lib/errors';
import type { Car, Group, Reservation, ReservationWrite } from '../lib/types';
import { addMinutes, nextQuarter, nowIn, weekStart } from '../lib/dates';
import { useCars, useGroup, useGroupId, useGroupMutation, useMemberNames, useReservation } from '../hooks/useGroupData';
import { useOnline } from '../hooks/useDrafts';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { CarSelect } from '../components/CarSelect';
import { MemberSelect } from '../components/MemberSelect';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function ReservationFormPage() {
  const { reservationId } = useParams();
  const id = reservationId ? Number(reservationId) : null;
  const group = useGroup();
  const cars = useCars();
  const reservation = useReservation(id);
  const queries = id ? [group, cars, reservation] : [group, cars];
  const state = queryState(queries, !!(group.data && cars.data && (id === null || reservation.data)));
  if (state) return state;
  return (
    <ReservationForm key={reservationId ?? 'new'} group={group.data!} cars={cars.data!} reservation={reservation.data} />
  );
}

/** The device's own time zone, to mention the group's only when they differ. */
function deviceTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return null;
  }
}

function ReservationForm({ group, cars, reservation }: { group: Group; cars: Car[]; reservation?: Reservation }) {
  const t = useT();
  const r = t.reservation;
  const f = useFormat();
  const me = useSession();
  const gid = useGroupId();
  const navigate = useNavigate();
  const name = useMemberNames();
  const online = useOnline();
  const { toast, confirm } = useFeedback();
  const [params] = useSearchParams();

  const now = nowIn(group.effective_timezone);
  const requestedDay = params.get('date');
  const defaultStart =
    requestedDay && DAY.test(requestedDay) && requestedDay > now.slice(0, 10) ? `${requestedDay}T08:00` : nextQuarter(now);
  const initialStart = reservation?.starts_at.slice(0, 16) ?? defaultStart;
  const initialEnd = reservation?.ends_at.slice(0, 16) ?? addMinutes(initialStart, 120);
  const activeCars = cars.filter((c) => !c.archived);
  const requestedCar = activeCars.find((c) => c.id === Number(params.get('car')));
  const [carId, setCarId] = useState<number | null>(
    reservation?.car_id ?? requestedCar?.id ?? (activeCars.length === 1 ? activeCars[0].id : null),
  );
  const [userId, setUserId] = useState<number | null>(reservation?.user_id ?? me.id);
  const [startDate, setStartDate] = useState(initialStart.slice(0, 10));
  const [startTime, setStartTime] = useState(initialStart.slice(11, 16));
  const [endDate, setEndDate] = useState(initialEnd.slice(0, 10));
  const [endTime, setEndTime] = useState(initialEnd.slice(11, 16));
  const [note, setNote] = useState(reservation?.note ?? '');
  const [localError, setLocalError] = useState('');

  const editing = reservation !== undefined;
  const mayChange =
    !reservation || group.my_role === 'admin' || reservation.created_by === me.id || reservation.user_id === me.id;
  const over = !!reservation && reservation.ends_at.slice(0, 16) <= now;
  const readOnly = !mayChange || over;

  const save = useGroupMutation<ReservationWrite, Reservation>(
    editing ? 'PUT' : 'POST',
    () => (reservation ? `/reservations/${reservation.id}` : '/reservations'),
    (body) => body,
  );
  const remove = useGroupMutation<void>('DELETE', () => `/reservations/${reservation?.id}`);

  const toCalendar = (day: string) => navigate(`/g/${gid}/calendar?week=${weekStart(day)}`);

  const chooseStartDate = (value: string) => {
    setStartDate(value);
    // Keep the end after the start when the day moves forward
    if (value && endDate < value) setEndDate(value);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (carId === null) return setLocalError(r.errors.car);
    if (userId === null) return setLocalError(r.errors.person);
    const startsAt = `${startDate}T${startTime}`;
    const endsAt = `${endDate}T${endTime}`;
    if (endsAt <= startsAt) return setLocalError(r.errors.endBeforeStart);
    setLocalError('');
    save.mutate(
      { car_id: carId, user_id: userId, starts_at: startsAt, ends_at: endsAt, note: note.trim() || null },
      {
        onSuccess: () => {
          toast(t.common.saved);
          toCalendar(startDate);
        },
      },
    );
  };

  const onDelete = async () => {
    if (!(await confirm(r.confirmDelete, { confirmLabel: t.common.delete, danger: true }))) return;
    remove.mutate(undefined, {
      onSuccess: () => {
        toast(t.common.deleted);
        toCalendar(reservation!.starts_at.slice(0, 10));
      },
    });
  };

  /** A clash names who has the car, which the generic error text cannot. */
  const describe = (error: unknown) => {
    if (error instanceof ApiError && isErrorDetail(error.detail) && error.detail.code === 'reservation_overlap') {
      const p = error.detail.params as { user_id: number; starts_at: string; ends_at: string };
      return r.overlap(name(p.user_id), f.span(p.starts_at, p.ends_at));
    }
    return errorText(error);
  };
  const error = localError || (save.isError ? describe(save.error) : remove.isError ? errorText(remove.error) : '');
  const zone = group.effective_timezone;

  return (
    <>
      <h1>{editing ? r.title : r.newTitle}</h1>
      {over && <div className="notice">{r.over}</div>}
      {!over && !mayChange && <div className="notice">{r.notYours}</div>}
      {!online && !readOnly && <div className="notice">{r.offline}</div>}
      <form className="form" onSubmit={submit} aria-describedby={error ? 'reservation-error' : undefined}>
        <fieldset disabled={readOnly} className="form plain">
          <CarSelect cars={cars} value={carId} onChange={setCarId} />
          <MemberSelect label={r.forWhom} members={group.members} value={userId} onChange={setUserId} />
          <div className="grid-2">
            <label className="field">
              <span>{r.fromDate}</span>
              <input type="date" value={startDate} onChange={(e) => chooseStartDate(e.target.value)} required />
            </label>
            <label className="field">
              <span>{r.time}</span>
              <input type="time" step={900} value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
            </label>
          </div>
          <div className="grid-2">
            <label className="field">
              <span>{r.toDate}</span>
              <input type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} required />
            </label>
            <label className="field">
              <span>{r.time}</span>
              <input type="time" step={900} value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
            </label>
          </div>
          {deviceTimezone() !== zone && <p className="subtle small m-0">{r.timezone(zone)}</p>}
          <label className="field">
            <span>{t.common.note} <span className="hint">{t.common.optional}</span></span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
          </label>
        </fieldset>
        {reservation && <p className="subtle small m-0">{r.enteredBy(name(reservation.created_by))}</p>}
        {error && <p id="reservation-error" className="error" role="alert">{error}</p>}
        <div className="button-row">
          {!readOnly && (
            <button type="submit" className="button primary" disabled={save.isPending || !online}>{t.common.save}</button>
          )}
          <button type="button" className="button" onClick={() => navigate(-1)}>{t.common.cancel}</button>
          {reservation && !readOnly && (
            <button type="button" className="button danger push-end" onClick={onDelete} disabled={remove.isPending || !online}>
              {t.common.delete}
            </button>
          )}
        </div>
      </form>
    </>
  );
}
