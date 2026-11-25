import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { errorText } from '../lib/api';
import { describeWarning } from '../lib/errors';
import type { Settlement } from '../lib/types';
import { useBalance, useGroup, useGroupId, useGroupMutation, useMemberNames, useSettlements } from '../hooks/useGroupData';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { BalanceTables } from '../components/BalanceTables';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';

export function SettlementPage() {
  const group = useGroup();
  const state = queryState([group], !!group.data);
  if (state) return state;
  return <SettlementPreview today={group.data!.today} />;
}

function SettlementPreview({ today }: { today: string }) {
  const t = useT();
  const s = t.settlement;
  const f = useFormat();
  const { confirm, toast } = useFeedback();
  const gid = useGroupId();
  const navigate = useNavigate();
  const name = useMemberNames();
  const [periodEnd, setPeriodEnd] = useState(today);
  const [acceptGaps, setAcceptGaps] = useState(false);
  const balance = useBalance(periodEnd);
  const settlements = useSettlements();
  const create = useGroupMutation<void, Settlement>('POST', () => '/settlements', () => ({ period_end: periodEnd, accept_warnings: acceptGaps }));

  const data = balance.data;
  const blocking = data?.warnings.some((w) => w.blocking) ?? false;
  const hasGaps = data?.warnings.some((w) => w.code === 'km_gap') ?? false;
  const empty = data ? data.trip_count + data.fuel_count + data.expense_count === 0 : true;
  const period = (start: string | null, end: string) => s.period(start ? f.date(start) : null, f.date(end));

  const onCreate = async () => {
    if (!(await confirm(s.confirmSettle(f.date(periodEnd)), { confirmLabel: s.settleNow }))) return;
    create.mutate(undefined, {
      onSuccess: (settlement) => {
        toast(s.created);
        navigate(`/g/${gid}/settlement/${settlement.id}`);
      },
    });
  };

  return (
    <>
      <h1>{s.title}</h1>
      <div className="card form">
        <label className="field">
          <span>{s.periodEnd}</span>
          <input type="date" value={periodEnd} max={today} onChange={(e) => setPeriodEnd(e.target.value)} />
        </label>
        {data && (
          <p className="subtle m-0">
            {s.summary(period(data.period_start, data.period_end), data.trip_count, data.fuel_count, data.expense_count, f.money(data.total_cost_cents))}
          </p>
        )}
      </div>

      {balance.isError ? queryState([balance], false) : !data && queryState([balance], false)}
      {data?.warnings.map((w) => (
        <div key={`${w.code}-${w.car_id ?? ''}-${w.from_km ?? ''}`} className="notice">
          {describeWarning(w, f)}
          {w.code === 'km_gap' && ` – ${s.gapHint}`}
        </div>
      ))}

      {data && <BalanceTables balance={data} />}

      {data && data.transfers.length > 0 && (
        <section className="card">
          <h2 className="mt-0">{s.transfers}</h2>
          <ul className="list">
            {data.transfers.map((tr) => (
              <li key={`${tr.from_user_id}-${tr.to_user_id}`} className="row">
                <span className="main">{s.pays(name(tr.from_user_id), name(tr.to_user_id))}</span>
                <strong className="num">{f.money(tr.amount_cents)}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data && !empty && (
        <div className="card form">
          {hasGaps && (
            <label className="check">
              <input type="checkbox" checked={acceptGaps} onChange={(e) => setAcceptGaps(e.target.checked)} />
              {s.acceptGaps}
            </label>
          )}
          {create.isError && <p className="error" role="alert">{errorText(create.error)}</p>}
          <button type="button" className="button primary" onClick={onCreate} disabled={create.isPending || blocking || (hasGaps && !acceptGaps)}>
            {s.settleNow}
          </button>
          {blocking && <p className="subtle small m-0">{s.finishTripsFirst}</p>}
        </div>
      )}
      {data && empty && <p className="subtle">{s.nothing}</p>}

      <h2>{s.previous}</h2>
      {settlements.data?.length === 0 && <p className="subtle">{s.none}</p>}
      {settlements.isError && queryState([settlements], false)}
      <ul className="list card">
        {settlements.data?.map((item) => (
          <li key={item.id}>
            <Link className="row" to={`/g/${gid}/settlement/${item.id}`}>
              <span className="main">
                <span className="title">{period(item.period_start, item.period_end)}</span>
                <div className="meta">{s.totalAmount(f.money(item.total_cost_cents))}</div>
              </span>
              {item.open_transfers > 0 ? <span className="badge accent">{s.open(item.open_transfers)}</span> : <span className="badge">{s.done}</span>}
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
