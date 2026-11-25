import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { errorText } from '../lib/api';
import { parseKm, parseMoney } from '../lib/format';
import type { Car, Group, Share, Trip, TripWrite } from '../lib/types';
import { useCars, useGroup, useGroupId, useGroupMutation, useTrip, useTrips } from '../hooks/useGroupData';
import { defaultCarId } from '../lib/cars';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { ShareEditor } from '../components/ShareEditor';
import { ExternalEditor, type ExternalDraft } from '../components/ExternalEditor';
import { newDraftKey } from '../lib/drafts';
import { CarSelect } from '../components/CarSelect';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';

export function TripFormPage() {
  const { tripId } = useParams();
  const id = tripId ? Number(tripId) : null;
  const group = useGroup();
  const cars = useCars();
  const trip = useTrip(id);
  // Recent trips decide which car to preselect for a new trip
  const trips = useTrips();
  const queries = id ? [group, cars, trip] : [group, cars, trips];
  const state = queryState(queries, !!(group.data && cars.data && (id ? trip.data : trips.data)));
  if (state) return state;
  return <TripForm key={tripId ?? 'new'} group={group.data!} cars={cars.data!} trip={trip.data} recentTrips={trips.data} />;
}

function TripForm({ group, cars, trip, recentTrips }: { group: Group; cars: Car[]; trip?: Trip; recentTrips?: Trip[] }) {
  const t = useT();
  const f = useFormat();
  const { toast, confirm } = useFeedback();
  const me = useSession();
  const gid = useGroupId();
  const navigate = useNavigate();
  const [carId, setCarId] = useState<number | null>(trip?.car_id ?? defaultCarId(cars, recentTrips, me.id));
  const car = cars.find((c) => c.id === carId);
  const [date, setDate] = useState(trip?.date ?? group.today);
  const [startKm, setStartKm] = useState(trip ? String(trip.start_km) : car ? String(car.last_km) : '');
  const [endKm, setEndKm] = useState(trip?.end_km != null ? String(trip.end_km) : '');
  const [note, setNote] = useState(trip?.note ?? '');
  const [shares, setShares] = useState<Share[]>(trip?.shares ?? [{ user_id: me.id, weight: 1 }]);
  const [external, setExternal] = useState<ExternalDraft[]>(
    trip?.external.map((e) => ({
      key: newDraftKey(),
      payer_name: e.payer_name,
      amount: f.moneyInput(e.amount_cents),
      received_by_user_id: e.received_by_user_id,
    })) ?? [],
  );
  const [localError, setLocalError] = useState('');
  const readOnly = trip?.settlement_id != null;

  const save = useGroupMutation<TripWrite>(trip ? 'PUT' : 'POST', () => (trip ? `/trips/${trip.id}` : '/trips'), (v) => v);
  const remove = useGroupMutation<void>('DELETE', () => `/trips/${trip?.id}`);

  const start = parseKm(startKm);
  const end = parseKm(endKm);
  const km = start !== null && end !== null ? end - start : null;
  const gap = !trip && car && start !== null && start > car.last_km ? start - car.last_km : 0;
  const starting = !endKm.trim() && !trip;

  const chooseCar = (id: number | null) => {
    setCarId(id);
    const chosen = cars.find((c) => c.id === id);
    if (!trip && chosen) setStartKm(String(chosen.last_km));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const e = t.trip.errors;
    if (carId === null) return setLocalError(e.car);
    if (start === null) return setLocalError(e.start);
    if (endKm.trim() && end === null) return setLocalError(e.endNotNumber);
    if (end !== null && end < start) return setLocalError(e.endBeforeStart);
    if (shares.length === 0) return setLocalError(e.noShares);
    const ext = external.map((row) => ({ ...row, cents: parseMoney(row.amount) }));
    if (ext.some((row) => row.cents === null || row.cents <= 0 || !row.payer_name.trim())) return setLocalError(e.external);
    setLocalError('');
    save.mutate(
      {
        car_id: carId,
        date,
        start_km: start,
        end_km: end,
        note: note.trim() || null,
        shares,
        external: ext.map((row) => ({ payer_name: row.payer_name.trim(), amount_cents: row.cents!, received_by_user_id: row.received_by_user_id })),
      },
      {
        onSuccess: () => {
          toast(starting ? t.trip.started : t.common.saved);
          navigate(`/g/${gid}`);
        },
      },
    );
  };

  const onDelete = async () => {
    if (!(await confirm(t.trip.confirmDelete, { confirmLabel: t.common.delete, danger: true }))) return;
    remove.mutate(undefined, {
      onSuccess: () => {
        toast(t.common.deleted);
        navigate(`/g/${gid}/history`);
      },
    });
  };

  const error = localError || (save.isError ? errorText(save.error) : remove.isError ? errorText(remove.error) : '');

  return (
    <>
      <h1>{trip ? t.trip.title : t.trip.newTitle}</h1>
      {readOnly && <div className="notice">{t.trip.settledNotice}</div>}
      <form className="form" onSubmit={submit} aria-describedby={error ? 'trip-error' : undefined}>
        <fieldset disabled={readOnly} className="form plain">
          <CarSelect cars={cars} value={carId} onChange={chooseCar} />
          <label className="field">
            <span>{t.common.date}</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <div className="grid-2">
            <label className="field">
              <span>{t.trip.startKm}</span>
              <input inputMode="numeric" value={startKm} onChange={(e) => setStartKm(e.target.value)} required />
            </label>
            <label className="field">
              <span>{t.trip.endKm}</span>
              <input inputMode="numeric" value={endKm} onChange={(e) => setEndKm(e.target.value)}
                placeholder={t.trip.endKmPlaceholder} autoFocus={!trip} />
            </label>
          </div>
          {km !== null && km >= 0 && <p className="subtle m-0">{t.trip.driven(f.km(km))}</p>}
          {gap > 0 && car && <div className="notice">{t.trip.gap(f.km(car.last_km), f.km(gap))}</div>}
          {starting && <p className="subtle small m-0">{t.trip.startHint}</p>}
          <ShareEditor members={group.members} value={shares} onChange={setShares} />
          <ExternalEditor members={group.members} defaultReceiver={me.id} value={external} onChange={setExternal} />
          <label className="field">
            <span>{t.common.note} <span className="hint">{t.common.optional}</span></span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder={t.trip.notePlaceholder} />
          </label>
        </fieldset>
        {trip?.cost_cents != null && <p className="subtle m-0">{t.trip.cost(f.money(trip.cost_cents), trip.cost_is_estimate)}</p>}
        {error && <p id="trip-error" className="error" role="alert">{error}</p>}
        <div className="button-row">
          {!readOnly && (
            <button type="submit" className="button primary" disabled={save.isPending}>
              {starting ? t.trip.start : t.common.save}
            </button>
          )}
          <button type="button" className="button" onClick={() => navigate(-1)}>{t.common.cancel}</button>
          {trip && !readOnly && (
            <button type="button" className="button danger push-end" onClick={onDelete} disabled={remove.isPending}>{t.common.delete}</button>
          )}
        </div>
      </form>
    </>
  );
}
