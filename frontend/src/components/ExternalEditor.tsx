import type { Member } from '../lib/types';
import { useT } from '../i18n';
import { useFormat } from '../hooks/useFormat';
import { newDraftKey } from '../lib/drafts';

export interface ExternalDraft {
  key: number;
  payer_name: string;
  amount: string;
  received_by_user_id: number;
}

interface Props {
  members: Member[];
  defaultReceiver: number;
  value: ExternalDraft[];
  onChange: (rows: ExternalDraft[]) => void;
}

/** Passengers outside the group who paid something for the trip. */
export function ExternalEditor({ members, defaultReceiver, value, onChange }: Props) {
  const t = useT();
  const format = useFormat();
  const update = (key: number, patch: Partial<ExternalDraft>) =>
    onChange(value.map((row) => (row.key === key ? { ...row, ...patch } : row)));

  return (
    <fieldset>
      <legend>{t.trip.external.legend}</legend>
      {value.length === 0 && <p className="subtle small mt-0">{t.trip.external.intro}</p>}
      {value.map((row) => (
        <div key={row.key} className="form mb-075">
          <div className="grid-2">
            <label className="field">
              <span>{t.common.name}</span>
              <input value={row.payer_name} onChange={(e) => update(row.key, { payer_name: e.target.value })} required />
            </label>
            <label className="field">
              <span>{t.common.amount(format.currencySymbol)}</span>
              <input inputMode="decimal" value={row.amount} onChange={(e) => update(row.key, { amount: e.target.value })} required />
            </label>
          </div>
          <div className="grid-2">
            <label className="field">
              <span>{t.trip.external.receivedBy}</span>
              <select value={row.received_by_user_id} onChange={(e) => update(row.key, { received_by_user_id: Number(e.target.value) })}>
                {members.filter((m) => m.active).map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
              </select>
            </label>
            <button type="button" className="button danger small align-end" onClick={() => onChange(value.filter((r) => r.key !== row.key))}>
              {t.common.remove}
            </button>
          </div>
        </div>
      ))}
      <button
        type="button"
        className="button small"
        onClick={() => onChange([...value, { key: newDraftKey(), payer_name: '', amount: '', received_by_user_id: defaultReceiver }])}
      >
        {t.trip.external.add}
      </button>
    </fieldset>
  );
}
