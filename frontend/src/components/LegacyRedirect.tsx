import { Navigate, useLocation } from 'react-router-dom';

// Paths of version 0.2 and earlier were German; bookmarks and home-screen links keep working
const LEGACY_SEGMENTS: [RegExp, string][] = [
  [/\/fahrt\/neu$/, '/trip/new'],
  [/\/fahrt\//, '/trip/'],
  [/\/tanken\/neu$/, '/fuel/new'],
  [/\/tanken\//, '/fuel/'],
  [/\/kosten\/neu$/, '/expense/new'],
  [/\/kosten\//, '/expense/'],
  [/\/verlauf$/, '/history'],
  [/\/abrechnung/, '/settlement'],
  [/\/gruppe$/, '/group'],
];
const LEGACY_TABS: Record<string, string> = { fahrten: 'trips', tanken: 'fuel', kosten: 'expenses' };

export function LegacyRedirect() {
  const location = useLocation();
  let path = location.pathname;
  for (const [pattern, replacement] of LEGACY_SEGMENTS) path = path.replace(pattern, replacement);
  const params = new URLSearchParams(location.search);
  const tab = params.get('tab');
  if (tab && LEGACY_TABS[tab]) params.set('tab', LEGACY_TABS[tab]);
  const search = params.toString();
  return <Navigate to={`${path}${search ? `?${search}` : ''}`} replace />;
}
