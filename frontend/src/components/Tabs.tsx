import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';

/** The selected tab, kept in ?tab= so a reload or the back button returns to it. */
function useTab<T extends string>(tabs: readonly T[]): [T, (next: T) => void] {
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab = tabs.includes(requested as T) ? (requested as T) : tabs[0];
  const select = (next: T) => setParams({ tab: next }, { replace: true });
  return [tab, select];
}

interface TabsProps<T extends string> {
  id: string;
  tabs: readonly T[];
  labels: Record<T, string>;
  /** Name of the tab list for screen readers */
  label: string;
  children: (tab: T) => ReactNode;
}

/** Tabs pattern: arrow keys move between tabs, Home/End jump to the ends. */
export function Tabs<T extends string>({ id, tabs, labels, label, children }: TabsProps<T>) {
  const [tab, select] = useTab(tabs);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent) => {
    const index = tabs.indexOf(tab);
    const moves: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    const next = tabs[(moves[event.key] + tabs.length) % tabs.length];
    select(next);
    buttons.current[tabs.indexOf(next)]?.focus();
  };

  return (
    <>
      <div className="tabs-inline" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
        {tabs.map((key, i) => (
          <button
            key={key}
            ref={(el) => {
              buttons.current[i] = el;
            }}
            id={`${id}-tab-${key}`}
            type="button"
            role="tab"
            className="chip"
            aria-selected={tab === key}
            aria-controls={`${id}-panel`}
            tabIndex={tab === key ? 0 : -1}
            onClick={() => select(key)}
          >
            {labels[key]}
          </button>
        ))}
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-tab-${tab}`}>
        {children(tab)}
      </div>
    </>
  );
}
