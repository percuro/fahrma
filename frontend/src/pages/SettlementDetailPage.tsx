import { useNavigate, useParams } from 'react-router-dom';
import { errorText } from '../lib/api';
import { useGroup, useGroupId, useGroupMutation, useMemberNames, useSettlement } from '../hooks/useGroupData';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';
import { BalanceTables } from '../components/BalanceTables';
import { useFeedback } from '../components/feedback-context';
import { queryState } from '../components/queryState';

export function SettlementDetailPage() {
  const t = useT();
  const s = t.settlement;
  const f = useFormat();
  const { confirm, toast } = useFeedback();
  const { settlementId } = useParams();
  const gid = useGroupId();
  const me = useSession();
  const navigate = useNavigate();
  const name = useMemberNames();
  const group = useGroup();
  const settlement = useSettlement(Number(settlementId));
  const markPaid = useGroupMutation<{ id: number }>('POST', ({ id }) => `/transfers/${id}/paid`);
  const markUnpaid = useGroupMutation<{ id: number }>('DELETE', ({ id }) => `/transfers/${id}/paid`);
  const remove = useGroupMutation<void>('DELETE', () => `/settlements/${settlementId}`);

  const state = queryState([settlement, group], !!(settlement.data && group.data));
  if (state) return state;
  const item = settlement.data!;
  const isAdmin = group.data!.my_role === 'admin';
  const period = s.period(item.period_start ? f.date(item.period_start) : null, f.date(item.period_end));

  const onRemove = async () => {
    if (!(await confirm(s.confirmUndo, { confirmLabel: s.undo, danger: true }))) return;
    remove.mutate(undefined, {
      onSuccess: () => {
        toast(s.undone);
        navigate(`/g/${gid}/settlement`);
      },
    });
  };

  return (
    <>
      <h1>{s.detailTitle(period)}</h1>
      <p className="subtle">{s.createdBy(f.date(item.created_at), name(item.created_by), f.money(item.result.total_cost_cents))}</p>

      <section className="card">
        <h2 className="mt-0">{s.transfers}</h2>
        {item.transfers.length === 0 && <p className="subtle">{s.allEven}</p>}
        <ul className="list">
          {item.transfers.map((tr) => {
            const involved = me.id === tr.from_user_id || me.id === tr.to_user_id || isAdmin;
            const paid = tr.paid_at !== null;
            return (
              <li key={tr.id} className="transfer">
                <span className="who">
                  {name(tr.from_user_id)} → {name(tr.to_user_id)}
                  {paid && <div className="subtle small">{s.paidOn(f.date(tr.paid_at))}</div>}
                </span>
                <strong className="num">{f.money(tr.amount_cents)}</strong>
                {involved && (
                  <button type="button" className={`button small ${paid ? '' : 'primary'}`}
                    onClick={() => (paid ? markUnpaid : markPaid).mutate({ id: tr.id! })}>
                    {paid ? s.undoPaid : s.markPaid}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        {(markPaid.isError || markUnpaid.isError) && <p className="error" role="alert">{errorText(markPaid.error ?? markUnpaid.error)}</p>}
      </section>

      <BalanceTables balance={item.result} />

      {isAdmin && item.is_latest && (
        <div className="button-row">
          <button type="button" className="button danger" onClick={onRemove} disabled={remove.isPending}>{s.undo}</button>
          {remove.isError && <p className="error" role="alert">{errorText(remove.error)}</p>}
        </div>
      )}
    </>
  );
}
