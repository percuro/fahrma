import type { Member, Share } from '../lib/types';
import { useT } from '../i18n';

interface Props {
  members: Member[];
  value: Share[];
  onChange: (shares: Share[]) => void;
}

/** Who bears the trip? Tap = included; +/− shifts the shares (e.g. 2:1). */
export function ShareEditor({ members, value, onChange }: Props) {
  const t = useT().trip.shares;
  const weightOf = (uid: number) => value.find((s) => s.user_id === uid)?.weight ?? 0;
  const toggle = (uid: number) =>
    onChange(weightOf(uid) ? value.filter((s) => s.user_id !== uid) : [...value, { user_id: uid, weight: 1 }]);
  const setWeight = (uid: number, weight: number) =>
    onChange(value.map((s) => (s.user_id === uid ? { ...s, weight: Math.max(1, Math.min(100, weight)) } : s)));
  const total = value.reduce((sum, s) => sum + s.weight, 0);
  const showWeights = value.length > 1;

  return (
    <fieldset>
      <legend>{t.legend}</legend>
      <div className="chips">
        {members.filter((m) => m.active).map((m) => (
          <button key={m.user_id} type="button" className="chip" aria-pressed={weightOf(m.user_id) > 0} onClick={() => toggle(m.user_id)}>
            {m.display_name}
          </button>
        ))}
      </div>
      {showWeights && (
        <ul className="list mt-05">
          {value.map((s) => {
            const name = members.find((m) => m.user_id === s.user_id)?.display_name ?? '?';
            return (
              <li key={s.user_id} className="row">
                <span className="main">{name}</span>
                <span className="subtle small num">{Math.round((s.weight / total) * 100)} %</span>
                <span className="weight" role="group" aria-label={t.weight(name)}>
                  <button type="button" aria-label={t.decrease(name)} onClick={() => setWeight(s.user_id, s.weight - 1)}>−</button>
                  <output className="num" aria-live="polite">{s.weight}</output>
                  <button type="button" aria-label={t.increase(name)} onClick={() => setWeight(s.user_id, s.weight + 1)}>+</button>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {value.length === 0 && <p className="subtle small">{t.atLeastOne}</p>}
    </fieldset>
  );
}
