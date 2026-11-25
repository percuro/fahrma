import { createContext, useContext } from 'react';
import type { Me } from '../lib/types';

export const SessionContext = createContext<Me | null>(null);

export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error('useSession used outside the signed-in app');
  return me;
}
