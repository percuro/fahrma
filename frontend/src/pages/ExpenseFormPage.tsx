import { useState, type FormEvent } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { errorText } from '../lib/api';
import { parseMoney } from '../lib/format';
import type { Allocation, Car, Expense, ExpenseWrite, Group, Trip } from '../lib/types';
import { findDraft, type Draft } from '../lib/outbox';
import { todayIn } from '../lib/dates';
import { useEntrySave, useSaveMessage, type PendingPhoto } from '../hooks/useDrafts';
import { DiscardDraftButton, DraftNotice } from '../components/DraftNotice';
import { useCars, useExpense, useGroup, useGroupId, useGroupMutation, useMemberNames, useTrips } from '../hooks/useGroupData';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { CarSelect } from '../components/CarSelect';
import { MemberSelect } from '../components/MemberSelect';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';
import { ReceiptSection } from '../components/ReceiptSection';

const CATEGORY_KEYS = ['other', 'insurance', 'tax', 'service', 'repair', 'inspection', 'tires', 'vignette', 'parking', 'toll', 'wash'];
const ALLOCATION_KEYS: Allocation[] = ['by_km', 'equal', 'single', 'trip'];

// Suggested split per category
const DEFAULT_ALLOCATION: Record<string, Allocation> = {
  insurance: 'equal', tax: 'equal', vignette: 'equal', inspection: 'equal',
  service: 'by_km', repair: 'by_km', tires: 'by_km', wash: 'equal',
  parking: 'trip', toll: 'trip', other: 'equal',
};

export function ExpenseFormPage() {
  const { expenseId } = useParams();
  const [params] = useSearchParams();
  const draft = findDraft(params.get('draft')) as Draft<'expense'> | undefined;
  const id = draft ? null : expenseId ? Number(expenseId) : null;
  const group = useGroup();
  const cars = useCars();
  const trips = useTrips();
  const entry = useExpense(id);
  const queries = id ? [group, cars, trips, entry] : [group, cars, trips];
  const state = queryState(queries, !!(group.data && cars.data && trips.data && (!id || entry.data)));
  if (state) return state;
  return (
    <ExpenseForm key={draft?.id ?? expenseId ?? 'new'} group={group.data!} cars={cars.data!} trips={trips.data!}
      entry={entry.data} draft={draft} />
  );
}

function ExpenseForm({ group, cars, trips, entry, draft }: {
  group: Group; cars: Car[]; trips: Trip[]; entry?: Expense; draft?: Draft<'expense'>;
}) {
  const t = useT();
  const x = t.expense;
  const f = useFormat();
  const { toast, confirm } = useFeedback();
  const me = useSession();
  const gid = useGroupId();
  const navigate = useNavigate();
  const name = useMemberNames();
  const activeCars = cars.filter((c) => !c.archived);
  const initial: ExpenseWrite | undefined = draft?.body ?? entry;
  const entityId = draft ? draft.entityId : (entry?.id ?? null);
  const editing = entityId !== null;
  const [category, setCategory] = useState(initial?.category ?? 'other');
  const [allocation, setAllocation] = useState<Allocation>(initial?.allocation ?? DEFAULT_ALLOCATION.other);
  const [carId, setCarId] = useState<number | null>(initial ? initial.car_id : activeCars.length === 1 ? activeCars[0].id : null);
  const [tripId, setTripId] = useState<number | null>(initial?.trip_id ?? null);
  const [date, setDate] = useState(initial?.date ?? todayIn(group.effective_timezone, group.today));
  const [amount, setAmount] = useState(f.moneyInput(initial?.amount_cents));
  const [description, setDescription] = useState(initial?.description ?? '');
  const [paidBy, setPaidBy] = useState<number | null>(initial?.paid_by_user_id ?? me.id);
  const [allocatedUser, setAllocatedUser] = useState<number | null>(initial?.allocated_user_id ?? me.id);
  const [localError, setLocalError] = useState('');
  const readOnly = !draft && entry?.settlement_id != null;

  const [photos, setPhotos] = useState<PendingPhoto[]>([]);
  const save = useEntrySave('expense', entityId, draft, photos);
  const saveMessage = useSaveMessage();
  const remove = useGroupMutation<void>('DELETE', () => `/expenses/${entry?.id}`);

  const finishedTrips = trips.filter((trip) => trip.end_km !== null).slice(0, 40);

  const chooseCategory = (value: string) => {
    setCategory(value);
    if (!editing) setAllocation(DEFAULT_ALLOCATION[value] ?? 'equal');
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const cents = parseMoney(amount);
    if (!cents || cents <= 0) return setLocalError(x.errors.amount);
    if (paidBy === null) return setLocalError(x.errors.payer);
    if (allocation === 'trip' && tripId === null) return setLocalError(x.errors.trip);
    setLocalError('');
    save.mutate(
      {
        category,
        allocation,
        date,
        amount_cents: cents,
        paid_by_user_id: paidBy,
        description: description.trim() || null,
        car_id: carId,
        trip_id: allocation === 'trip' ? tripId : null,
        allocated_user_id: allocation === 'single' ? allocatedUser : null,
      },
      {
        onSuccess: (outcome) => {
          toast(saveMessage(outcome, save.photoError));
          navigate(`/g/${gid}`);
        },
      },
    );
  };

  const onDelete = async () => {
    if (!(await confirm(x.confirmDelete, { confirmLabel: t.common.delete, danger: true }))) return;
    remove.mutate(undefined, {
      onSuccess: () => {
        toast(t.common.deleted);
        navigate(`/g/${gid}/history?tab=expenses`);
      },
    });
  };

  const error = localError || (save.isError ? errorText(save.error) : remove.isError ? errorText(remove.error) : '');

  return (
    <>
      <h1>{editing ? x.title : x.newTitle}</h1>
      {draft && <DraftNotice draft={draft} />}
      {readOnly && <div className="notice">{x.settledNotice}</div>}
      <form className="form" onSubmit={submit}>
        <fieldset disabled={readOnly} className="form plain">
          <div className="grid-2">
            <label className="field">
              <span>{x.category}</span>
              <select value={category} onChange={(e) => chooseCategory(e.target.value)}>
                {CATEGORY_KEYS.map((key) => <option key={key} value={key}>{x.categories[key]}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t.common.amount(f.currencySymbol)}</span>
              <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required autoFocus={!editing} />
            </label>
          </div>
          <label className="field">
            <span>{x.description} <span className="hint">{t.common.optional}</span></span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} />
          </label>
          <div className="grid-2">
            <MemberSelect label={t.common.paidBy} members={group.members} value={paidBy} onChange={setPaidBy} />
            <label className="field">
              <span>{t.common.date}</span>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </label>
          </div>
          {activeCars.length > 1 && <CarSelect cars={cars} value={carId} onChange={setCarId} optional />}
          <fieldset>
            <legend>{x.whoBears}</legend>
            {ALLOCATION_KEYS.map((key) => (
              <label key={key} className="check radio">
                <input type="radio" name="allocation" value={key} checked={allocation === key} onChange={() => setAllocation(key)} />
                <span><strong>{x.allocations[key].label}</strong><br /><span className="subtle small">{x.allocations[key].help}</span></span>
              </label>
            ))}
          </fieldset>
          {allocation === 'single' && (
            <MemberSelect label={t.common.person} members={group.members} value={allocatedUser} onChange={setAllocatedUser} />
          )}
          {allocation === 'trip' && (finishedTrips.length === 0 ? (
            <p className="notice m-0">{x.noFinishedTrips}</p>
          ) : (
            <label className="field">
              <span>{x.trip}</span>
              <select value={tripId ?? ''} onChange={(e) => setTripId(Number(e.target.value))} required>
                <option value="" disabled>{t.common.pleaseChoose}</option>
                {finishedTrips.map((trip) => (
                  <option key={trip.id} value={trip.id}>
                    {[f.date(trip.date), trip.shares.map((s) => name(s.user_id)).join(' + '), f.km(trip.km), trip.note].filter(Boolean).join(' · ')}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
        <ReceiptSection kind="expense" entryId={draft ? draft.entityId : (entry?.id ?? null)} receipts={draft ? [] : (entry?.receipts ?? [])}
          draftId={draft?.id} pending={photos} onPendingChange={setPhotos} canDelete={!readOnly} />
        {error && <p className="error" role="alert">{error}</p>}
        <div className="button-row">
          {!readOnly && <button type="submit" className="button primary" disabled={save.isPending}>{t.common.save}</button>}
          <button type="button" className="button" onClick={() => navigate(-1)}>{t.common.cancel}</button>
          {draft && <DiscardDraftButton draft={draft} />}
          {!draft && entry && !readOnly && (
            <button type="button" className="button danger push-end" onClick={onDelete} disabled={remove.isPending}>{t.common.delete}</button>
          )}
        </div>
      </form>
    </>
  );
}
