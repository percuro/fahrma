import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { errorText } from '../lib/api';
import { parseKm, parseMoney, parseQuantity } from '../lib/format';
import { defaultCarId, energyKind } from '../lib/cars';
import type { Car, Fuel, FuelWrite, Group, Trip } from '../lib/types';
import { useCars, useFuelEntry, useGroup, useGroupId, useGroupMutation, useTrips } from '../hooks/useGroupData';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { CarSelect } from '../components/CarSelect';
import { MemberSelect } from '../components/MemberSelect';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';

export function FuelFormPage() {
  const { fuelId } = useParams();
  const id = fuelId ? Number(fuelId) : null;
  const group = useGroup();
  const cars = useCars();
  const entry = useFuelEntry(id);
  const trips = useTrips();
  const queries = id ? [group, cars, entry] : [group, cars, trips];
  const state = queryState(queries, !!(group.data && cars.data && (id ? entry.data : trips.data)));
  if (state) return state;
  return <FuelForm key={fuelId ?? 'new'} group={group.data!} cars={cars.data!} entry={entry.data} recentTrips={trips.data} />;
}

function FuelForm({ group, cars, entry, recentTrips }: { group: Group; cars: Car[]; entry?: Fuel; recentTrips?: Trip[] }) {
  const t = useT();
  const f = useFormat();
  const { toast, confirm } = useFeedback();
  const me = useSession();
  const gid = useGroupId();
  const navigate = useNavigate();
  const [carId, setCarId] = useState<number | null>(entry?.car_id ?? defaultCarId(cars, recentTrips, me.id));
  const [date, setDate] = useState(entry?.date ?? group.today);
  const [amount, setAmount] = useState(f.moneyInput(entry?.amount_cents));
  const [quantity, setQuantity] = useState(f.quantityInput(entry?.quantity_milli));
  const [odometer, setOdometer] = useState(entry?.odometer_km != null ? String(entry.odometer_km) : '');
  const [paidBy, setPaidBy] = useState<number | null>(entry?.paid_by_user_id ?? me.id);
  const [fullTank, setFullTank] = useState(entry?.full_tank ?? true);
  const [note, setNote] = useState(entry?.note ?? '');
  const [localError, setLocalError] = useState('');
  const readOnly = entry?.settlement_id != null;

  const car = cars.find((c) => c.id === carId);
  // Unknown car (several to choose from): label by what the group has
  const unit = car?.energy_unit ?? (energyKind(cars) === 'charge' ? 'kWh' : 'l');
  const electric = unit === 'kWh';

  const save = useGroupMutation<FuelWrite>(entry ? 'PUT' : 'POST', () => (entry ? `/fuel/${entry.id}` : '/fuel'), (v) => v);
  const remove = useGroupMutation<void>('DELETE', () => `/fuel/${entry?.id}`);

  const cents = parseMoney(amount);
  const milli = parseQuantity(quantity);
  const price = cents && milli ? f.unitPrice(cents, milli, unit) : null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const e = t.fuel.errors;
    if (carId === null) return setLocalError(e.car);
    if (!cents || cents <= 0) return setLocalError(e.amount);
    if (quantity.trim() && milli === null) return setLocalError(e.quantity);
    if (odometer.trim() && parseKm(odometer) === null) return setLocalError(e.odometer);
    if (paidBy === null) return setLocalError(e.payer);
    setLocalError('');
    save.mutate(
      {
        car_id: carId,
        date,
        amount_cents: cents,
        quantity_milli: milli,
        odometer_km: parseKm(odometer),
        paid_by_user_id: paidBy,
        full_tank: fullTank,
        note: note.trim() || null,
      },
      {
        onSuccess: () => {
          toast(t.common.saved);
          navigate(`/g/${gid}`);
        },
      },
    );
  };

  const onDelete = async () => {
    if (!(await confirm(t.fuel.confirmDelete, { confirmLabel: t.common.delete, danger: true }))) return;
    remove.mutate(undefined, {
      onSuccess: () => {
        toast(t.common.deleted);
        navigate(`/g/${gid}/history?tab=fuel`);
      },
    });
  };

  const error = localError || (save.isError ? errorText(save.error) : remove.isError ? errorText(remove.error) : '');
  const title = entry
    ? electric ? t.fuel.titleChargeEntry : t.fuel.titleEntry
    : !car && energyKind(cars) === 'both' ? t.dashboard.fuelOrCharge : electric ? t.fuel.titleCharge : t.fuel.titleFuel;

  return (
    <>
      <h1>{title}</h1>
      {readOnly && <div className="notice">{t.fuel.settledNotice}</div>}
      <form className="form" onSubmit={submit}>
        <fieldset disabled={readOnly} className="form plain">
          <CarSelect cars={cars} value={carId} onChange={setCarId} />
          <div className="grid-2">
            <label className="field">
              <span>{t.common.amount(f.currencySymbol)}</span>
              <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required autoFocus={!entry} />
            </label>
            <label className="field">
              <span>{t.fuel.quantity(unit)} <span className="hint">{t.common.optional}</span></span>
              <input inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </label>
          </div>
          {price && <p className="subtle small m-0">{price}</p>}
          <MemberSelect label={t.common.paidBy} members={group.members} value={paidBy} onChange={setPaidBy} />
          <div className="grid-2">
            <label className="field">
              <span>{t.common.date}</span>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </label>
            <label className="field">
              <span>{t.fuel.odometer} <span className="hint">{t.common.optional}</span></span>
              <input inputMode="numeric" value={odometer} onChange={(e) => setOdometer(e.target.value)} />
            </label>
          </div>
          <label className="check">
            <input type="checkbox" checked={fullTank} onChange={(e) => setFullTank(e.target.checked)} />
            {electric ? t.fuel.fullCharge : t.fuel.fullTank}
          </label>
          <label className="field">
            <span>{t.common.note} <span className="hint">{t.common.optional}</span></span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
          </label>
        </fieldset>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="button-row">
          {!readOnly && <button type="submit" className="button primary" disabled={save.isPending}>{t.common.save}</button>}
          <button type="button" className="button" onClick={() => navigate(-1)}>{t.common.cancel}</button>
          {entry && !readOnly && (
            <button type="button" className="button danger push-end" onClick={onDelete} disabled={remove.isPending}>{t.common.delete}</button>
          )}
        </div>
      </form>
    </>
  );
}
