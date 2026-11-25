import type { Car } from '../lib/types';
import { useT } from '../i18n';

interface Props {
  cars: Car[];
  value: number | null;
  onChange: (id: number | null) => void;
  optional?: boolean;
}

export function CarSelect({ cars, value, onChange, optional }: Props) {
  const t = useT();
  const visible = cars.filter((c) => !c.archived || c.id === value);
  if (visible.length === 1 && !optional) {
    return <p className="subtle m-0">{t.common.car}: <strong>{visible[0].name}</strong></p>;
  }
  return (
    <label className="field">
      <span>{t.common.car}</span>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} required={!optional}>
        <option value="" disabled={!optional}>{optional ? t.expense.noCar : t.common.pleaseChoose}</option>
        {visible.map((c) => <option key={c.id} value={c.id}>{c.name}{c.plate ? ` (${c.plate})` : ''}</option>)}
      </select>
    </label>
  );
}
