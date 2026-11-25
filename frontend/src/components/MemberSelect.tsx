import type { Member } from '../lib/types';
import { useT } from '../i18n';

interface Props {
  label: string;
  members: Member[];
  value: number | null;
  onChange: (id: number) => void;
}

export function MemberSelect({ label, members, value, onChange }: Props) {
  const t = useT();
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value ?? ''} onChange={(e) => onChange(Number(e.target.value))} required>
        <option value="" disabled>{t.common.pleaseChoose}</option>
        {members.filter((m) => m.active || m.user_id === value).map((m) => (
          <option key={m.user_id} value={m.user_id}>{m.display_name}</option>
        ))}
      </select>
    </label>
  );
}
